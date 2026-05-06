"""
hermes.py — Top-level orchestrator for the Hermes algorithmic trading platform.

Responsibilities:
  - Load agent configs from disk and instantiate trading agents via the factory.
  - Build and run a shared DataFeed that streams price data for all traded symbols.
  - Run each agent in its own asyncio task with crash-recovery backoff.
  - Maintain a daily counter-reset loop and an optional HTTP dashboard.
  - Expose a kill switch that liquidates all open positions and signals systemd
    to not restart the process (exit code 99).
  - Send Telegram notifications on startup, agent failures, and kill-switch events.
  - Initialize the portfolio-level RiskManager and share it with every agent.
  - Provide a CLI test mode (`--test-one SYMBOL`) that runs one full evaluation
    cycle for a single agent with verbose logging.
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_BASE = Path(__file__).parent.parent
sys.path.insert(0, str(_BASE))   # make project root importable from any cwd

from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
load_dotenv(_BASE / ".env")

# ── Logging setup ──────────────────────────────────────────────────────────────
# Must happen before any other imports that create loggers.

def _make_log_dir() -> Path:
    """Return the first writable log directory, falling back to <project>/logs.

    `mkdir(exist_ok=True)` succeeds on a pre-existing dir even when our
    process can't write to it; we therefore probe with a sentinel touch.
    """
    for candidate in (Path("/var/log/hermes"), _BASE / "logs"):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            sentinel = candidate / ".write_test"
            sentinel.touch(exist_ok=True)
            sentinel.unlink(missing_ok=True)
            return candidate
        except (PermissionError, OSError):
            continue
    return _BASE / "logs"


LOG_DIR = _make_log_dir()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-22s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "hermes.log"),
    ],
)
log = logging.getLogger("hermes")

# ── Project imports (after .env is loaded) ─────────────────────────────────────

from agents.base_agent import BaseAgent, DRY_RUN
from agents.factory import create_agent
from core.config_loader import load_all_agents
from core.data_feed import DataFeed, SymbolMeta
from core.reconciliation import reconcile_agent_positions
from core.risk_manager import get_risk_manager
from notifications import telegram

BACKOFF_DELAYS = [10, 30, 60]   # seconds between crash restarts; agent suspended after 3 failures


class Hermes:
    """
    Central coordinator that owns the DataFeed, all trading agents, and the
    asyncio task graph for the lifetime of the process.
    """

    def __init__(self):
        self.agents: list[BaseAgent] = []
        self.feed: DataFeed | None = None
        # Setting this event triggers graceful shutdown across all tasks.
        self.kill_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._daily_reset: date = date.today()
        # Portfolio-level risk gate, shared by every agent.
        self.risk_manager = get_risk_manager(
            max_daily_loss_pct=float(os.getenv("HERMES_MAX_DAILY_LOSS_PCT", "3.0")),
            max_total_drawdown_pct=float(os.getenv("HERMES_MAX_DRAWDOWN_PCT", "10.0")),
        )

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_agent_logger(self, agent: BaseAgent) -> None:
        """Attach a per-agent file handler so each agent writes to its own log file."""
        safe_name = agent.name.lower().replace(" ", "_")
        handler = logging.FileHandler(LOG_DIR / f"{safe_name}.log")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(message)s"
        ))
        agent.log.addHandler(handler)
        agent.log.propagate = True   # also flows to hermes.log + stdout

    def load_agents(self) -> None:
        """Instantiate all agents from YAML configs and attach their loggers."""
        config_dir = _BASE / "config" / "agents"
        configs = load_all_agents(config_dir)
        for cfg in configs:
            try:
                agent = create_agent(cfg, feed=self.feed, risk_manager=self.risk_manager)
                self._setup_agent_logger(agent)
                self.agents.append(agent)
                log.info("Loaded: %-22s %s", cfg.name, cfg.symbol)
            except Exception as exc:
                log.error("Failed to load agent %s: %s", cfg.name, exc)

    def build_feed(self, configs) -> DataFeed:
        """Construct a DataFeed covering every symbol referenced by the given configs."""
        from agents.base_agent import AgentConfig
        symbols = [
            SymbolMeta(
                symbol=c.symbol,
                asset_type=c.asset_type,
                timezone=c.timezone,
                active_hours_start=c.active_hours_start,
                active_hours_end=c.active_hours_end,
            )
            for c in configs
        ]
        return DataFeed(symbols)

    # ── Agent tasks ────────────────────────────────────────────────────────────

    async def _run_agent(self, agent: BaseAgent) -> None:
        """Run one agent with exponential backoff on crash. Stops after 3 failures."""
        crash_count = 0
        while not self.kill_event.is_set():
            try:
                await agent.tick(self.kill_event)
                await asyncio.sleep(agent.cfg.check_interval_seconds)
                crash_count = 0
            except asyncio.CancelledError:
                break
            except Exception as exc:
                crash_count += 1
                delay = BACKOFF_DELAYS[min(crash_count - 1, len(BACKOFF_DELAYS) - 1)]
                log.error("Agent '%s' crash #%d: %s  (retry in %ds)", agent.name, crash_count, exc, delay)
                if crash_count > len(BACKOFF_DELAYS):
                    log.error("Agent '%s' suspended after %d crashes", agent.name, crash_count)
                    agent.paused_manually = True
                    telegram.send(
                        f"⚠️ <b>{agent.name}</b> suspended after {crash_count} crashes\n"
                        f"Last error: <code>{exc}</code>"
                    )
                    break
                await asyncio.sleep(delay)

    async def _restart_agent(self, agent: BaseAgent) -> None:
        """Called from dashboard to restart a single agent task."""
        agent.paused_manually = False
        task = asyncio.create_task(self._run_agent(agent), name=agent.name)
        self._tasks.append(task)
        log.info("Agent '%s' restarted", agent.name)

    # ── Support tasks ──────────────────────────────────────────────────────────

    async def _daily_reset_loop(self) -> None:
        """Poll every minute and trigger each agent's daily counter reset at midnight."""
        while not self.kill_event.is_set():
            for agent in self.agents:
                self._daily_reset = agent.reset_daily_counters_if_new_day(self._daily_reset)
            await asyncio.sleep(60)

    async def _daily_ai_briefing_loop(self) -> None:
        """Run AI daily summary at 08:00 UTC (Hermes Block 7)."""
        while not self.kill_event.is_set():
            now = datetime.now(timezone.utc)
            next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now >= next_run:
                next_run = next_run + timedelta(days=1)
            wait_s = max(1.0, (next_run - now).total_seconds())
            try:
                await asyncio.wait_for(self.kill_event.wait(), timeout=wait_s)
                break
            except asyncio.TimeoutError:
                pass
            if self.kill_event.is_set():
                break
            try:
                from core.daily_summary import generate_daily_summary

                await generate_daily_summary(force_refresh=False)
                log.info("Daily AI briefing generated for %s UTC", date.today().isoformat())
            except Exception as exc:  # noqa: BLE001
                log.warning("Daily AI briefing failed: %s", exc)

    async def _daily_rebalance_loop(self) -> None:
        """Optional auto-rebalance at configured UTC time (portfolio.yaml)."""
        from core.rebalancer import PortfolioRebalancer, load_rebalancing_config

        while not self.kill_event.is_set():
            cfg = load_rebalancing_config(_BASE / "config" / "portfolio.yaml")
            if not cfg.get("enabled") or not cfg.get("auto_rebalance"):
                try:
                    await asyncio.wait_for(self.kill_event.wait(), timeout=3600)
                except asyncio.TimeoutError:
                    pass
                continue
            t = str(cfg.get("check_time") or "09:00")
            try:
                th, tm = [int(x) for x in t.split(":")[:2]]
            except ValueError:
                th, tm = 9, 0
            now = datetime.now(timezone.utc)
            nxt = now.replace(hour=th, minute=tm, second=0, microsecond=0)
            if now >= nxt:
                nxt = nxt + timedelta(days=1)
            wait_s = max(1.0, (nxt - now).total_seconds())
            try:
                await asyncio.wait_for(self.kill_event.wait(), timeout=wait_s)
                break
            except asyncio.TimeoutError:
                pass
            if self.kill_event.is_set():
                break
            try:
                key = os.getenv("ALPACA_API_KEY", "")
                sec = os.getenv("ALPACA_API_SECRET", "")
                paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"
                tc = TradingClient(key, sec, paper=paper) if key and sec else None
                rb = PortfolioRebalancer.from_yaml(tc, _BASE / "config" / "portfolio.yaml")
                drift = rb.check_drift_sync()
                if drift.get("needs_rebalance"):
                    orders = rb.rebalance_sync(dry_run=False)
                    log.info("Auto-rebalance executed: %d orders", len(orders))
            except Exception as exc:  # noqa: BLE001
                log.warning("Auto-rebalance failed: %s", exc)

    # ── Kill switch ────────────────────────────────────────────────────────────

    async def activate_kill_switch(self) -> None:
        """
        Emergency stop: set the shared kill event so all agent loops exit, then
        immediately submit market SELL orders for every open position.  Idempotent —
        calling it a second time while already activated is a no-op.
        """
        already = self.kill_event.is_set()
        self.kill_event.set()
        if already:
            return
        log.warning("KILL SWITCH ACTIVATED — closing all positions")
        for agent in self.agents:
            if agent.position_qty > 0:
                try:
                    agent.submit_order("SELL", agent.position_qty)
                except Exception as exc:
                    log.error("Kill switch SELL failed for %s: %s", agent.name, exc)
        summary = ", ".join(
            f"{a.name}: ${a.position_qty * (a.prices[-1] if a.prices else 0):.0f}"
            for a in self.agents if a.position_qty > 0
        ) or "no open positions"
        telegram.send(f"🛑 <b>KILL SWITCH</b> activated\n{summary}")
        log.warning("Kill switch complete.")

    # ── Main entry ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Main async entry point.  Execution order:
          1. Safety check — refuse live trading unless the operator has explicitly
             opted in via HERMES_LIVE_CONFIRM=I_UNDERSTAND.
          2. Load configs → build DataFeed → bootstrap historical prices.
          3. Instantiate agents and reconcile their positions against the broker.
          4. Register SIGTERM handler so systemd stop triggers the kill switch.
          5. Launch all asyncio tasks (feed, daily-reset, per-agent loops, dashboard).
          6. Wait for all tasks to finish; exit 99 if stopped via kill switch so
             systemd does not automatically restart the service.
        """
        if not DRY_RUN and os.getenv("ALPACA_PAPER", "true").lower() == "false":
            if os.getenv("HERMES_LIVE_CONFIRM", "") != "I_UNDERSTAND":
                log.error(
                    "Refusing LIVE trading: set HERMES_LIVE_CONFIRM=I_UNDERSTAND in .env"
                )
                sys.exit(2)

        dry = "[DRY-RUN] " if DRY_RUN else ""
        log.info("=" * 60)
        log.info("Hermes Trading Platform starting  %s", dry)
        log.info("=" * 60)
        log.info("RiskManager: %s", self.risk_manager.status())

        # Build DataFeed first so agents can reference it
        config_dir = _BASE / "config" / "agents"
        all_configs = load_all_agents(config_dir)
        if not all_configs:
            log.error("No agent configs found in %s. Exiting.", config_dir)
            sys.exit(1)

        self.feed = self.build_feed(all_configs)
        log.info("Bootstrapping price history...")
        self.feed.bootstrap()

        self.load_agents()
        if not self.agents:
            log.error("No agents loaded. Exiting.")
            sys.exit(1)

        # Sync each agent's local price list from feed
        for agent in self.agents:
            agent.bootstrap_price_history()

        try:
            reconcile_agent_positions(self.agents)
        except Exception as exc:
            log.warning("Reconciliation error: %s", exc)

        # SIGTERM → graceful shutdown (systemd stop)
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(
            signal.SIGTERM,
            lambda: asyncio.create_task(self.activate_kill_switch()),
        )

        # Launch all tasks
        self._tasks = [
            asyncio.create_task(self.feed.run(interval_seconds=60), name="data_feed"),
            asyncio.create_task(self._daily_reset_loop(), name="daily_reset"),
            asyncio.create_task(self._daily_ai_briefing_loop(), name="daily_ai_briefing"),
            asyncio.create_task(self._daily_rebalance_loop(), name="daily_rebalance"),
        ] + [
            asyncio.create_task(self._run_agent(agent), name=agent.name)
            for agent in self.agents
        ]

        if os.getenv("HERMES_DASHBOARD_ENABLE", "true").lower() in ("1", "true", "yes"):
            if os.getenv("DASHBOARD_API_KEY", "").strip():
                self._tasks.append(asyncio.create_task(self._run_dashboard(), name="dashboard"))
            else:
                log.warning("Dashboard not started: set DASHBOARD_API_KEY in .env")

        mode_str = "DRY-RUN (no real orders)" if DRY_RUN else "LIVE TRADING"
        log.info("All %d agents running in %s mode.", len(self.agents), mode_str)
        telegram.send(
            f"🟢 <b>Hermes started</b> — {len(self.agents)} agents | "
            f"{'🔇 DRY-RUN' if DRY_RUN else '💰 LIVE'}"
        )

        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass

        if self.kill_event.is_set():
            log.info("Hermes stopped via kill switch.")
            sys.exit(99)   # RestartPreventExitStatus=99 in systemd

    async def _run_dashboard(self) -> None:
        """Start the uvicorn HTTP server that serves the monitoring dashboard."""
        import uvicorn
        from core.dashboard_app import create_dashboard_app

        app = create_dashboard_app(self)
        config = uvicorn.Config(
            app,
            host=os.getenv("DASHBOARD_HOST", "0.0.0.0"),
            port=int(os.getenv("DASHBOARD_PORT", "8080")),
            log_level="warning",
        )
        server = uvicorn.Server(config)
        log.info(
            "Dashboard on http://%s:%s",
            os.getenv("DASHBOARD_HOST", "0.0.0.0"),
            os.getenv("DASHBOARD_PORT", "8080"),
        )
        await server.serve()


async def run_test_one(symbol: str, with_llm: bool = False) -> int:
    """One-shot debug mode: run a single evaluation cycle for one agent and
    print everything we would consider before placing a trade.

    Does NOT submit any orders.  Honours DRY_RUN regardless.
    """
    log.info("=" * 60)
    log.info("TEST-ONE for symbol=%s  with_llm=%s", symbol, with_llm)
    log.info("=" * 60)

    config_dir = _BASE / "config" / "agents"
    all_configs = load_all_agents(config_dir)
    target = next((c for c in all_configs if c.symbol == symbol), None)
    if target is None:
        log.error("No agent config found for symbol %r. Available: %s",
                  symbol, [c.symbol for c in all_configs])
        return 2

    # Build a minimal feed for just this symbol so prices bootstrap fast.
    feed = DataFeed([SymbolMeta(
        symbol=target.symbol, asset_type=target.asset_type, timezone=target.timezone,
        active_hours_start=target.active_hours_start,
        active_hours_end=target.active_hours_end,
    )])
    log.info("Bootstrapping feed for %s...", target.symbol)
    feed.bootstrap()

    risk_manager = get_risk_manager()
    agent = create_agent(target, feed=feed, risk_manager=risk_manager)
    agent.bootstrap_price_history()

    # Reconcile so we know if there's an open position already.
    try:
        reconcile_agent_positions([agent])
    except Exception as exc:
        log.warning("Reconciliation error: %s", exc)

    # Single evaluation pass (no trade).
    debug = await agent.evaluate_once()
    print("\n=== EVALUATE_ONCE OUTPUT ===")
    print(json.dumps(debug, indent=2, default=str))

    if with_llm:
        log.info("Asking LLM for full decision...")
        # Build a synthetic SignalResult and call the advisor directly.
        from core.llm_advisor import get_llm_advisor
        from agents.base_agent import SignalResult
        rule = SignalResult(
            direction=debug["rule_signal"]["direction"],
            confidence=debug["rule_signal"]["confidence"],
            reason=debug["rule_signal"]["reason"],
        )
        advisor = get_llm_advisor()
        if not advisor.is_configured():
            print("\nANTHROPIC_API_KEY not set — skipping LLM call.")
            return 0
        new_sig, meta = await advisor.review_signal(agent, rule)
        print("\n=== LLM DECISION ===")
        print(json.dumps({
            "direction": new_sig.direction,
            "confidence": new_sig.confidence,
            "reason": new_sig.reason,
            "position_size_pct": new_sig.position_size_pct,
            "stop_loss_pct": new_sig.stop_loss_pct,
            "take_profit_pct": new_sig.take_profit_pct,
            "meta": meta,
        }, indent=2, default=str))

    log.info("Risk manager status: %s", risk_manager.status())
    log.info("TEST-ONE complete (no orders submitted)")
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Hermes orchestrator")
    p.add_argument(
        "--test-one",
        metavar="SYMBOL",
        help="Run a one-shot evaluation cycle for the given symbol (e.g. 'BTC/USD'). No orders submitted.",
    )
    p.add_argument(
        "--with-llm",
        action="store_true",
        help="When used with --test-one, also call the LLM advisor for a full decision.",
    )
    return p.parse_args()


def main() -> None:
    """Synchronous entry point — wraps the async run() for use as a CLI command."""
    args = _parse_args()
    if args.test_one:
        try:
            rc = asyncio.run(run_test_one(args.test_one, with_llm=args.with_llm))
        except KeyboardInterrupt:
            rc = 130
        sys.exit(rc)

    hermes = Hermes()
    try:
        asyncio.run(hermes.run())
    except KeyboardInterrupt:
        log.info("Hermes stopped (KeyboardInterrupt).")


if __name__ == "__main__":
    main()
