"""
Swarm bootstrap — runs once at app startup.

Responsibilities
----------------
1. Hydrate Redis cache from Postgres `agent_registry` (cold-start safety).
2. Seed default swarms from `swarm_definitions.DEFAULT_SWARMS`.
3. Register all existing `trading_agents` from DB as Trade Execution swarm
   members (so they appear in the swarm registry without manual onboarding).
4. Start the in-process Orchestra scheduler (cheap thread) which
   `enqueues orchestra_tick` every 30s on the Dramatiq broker.

Idempotent — safe to call multiple times.
"""
from __future__ import annotations

import logging
import os
import threading
import time

from sqlalchemy import text

try:
    from core.swarm_definitions import DEFAULT_SWARMS
    from core.swarm_registry import get_engine, swarm_registry
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from hermes.core.swarm_definitions import DEFAULT_SWARMS
    from hermes.core.swarm_registry import get_engine, swarm_registry

log = logging.getLogger(__name__)

_BOOTSTRAPPED = False
_LOCK = threading.Lock()


# ── Step 1+2 — hydrate + seed defaults ────────────────────────────────────
def hydrate_and_seed() -> dict[str, int]:
    hydrated = swarm_registry.hydrate_from_db()

    seeded = 0
    for swarm in DEFAULT_SWARMS:
        for agent in swarm["agents"]:
            existing = swarm_registry.get_agent(agent["agent_id"])
            if existing:
                continue
            swarm_registry.register_agent(
                agent_id=agent["agent_id"],
                name=agent["name"],
                swarm=swarm["swarm_name"],
                capabilities=agent.get("capabilities", []),
                agent_type=agent.get("agent_type", "worker"),
                priority=agent.get("priority", 5),
                config={"agent_type": agent.get("agent_type", "worker")},
                metadata={
                    "icon": swarm.get("icon"),
                    "color": swarm.get("color"),
                    "swarm_display_name": swarm.get("display_name"),
                },
            )
            seeded += 1

    # Step 3: register trading_agents into "trading" swarm
    trading = _register_trading_agents()
    user_agents = _register_user_agents()

    # Step 4: register domain task handlers
    handlers_count = 0
    try:
        try:
            from core.swarm_handlers import register_all
        except ModuleNotFoundError:
            from hermes.core.swarm_handlers import register_all
        registered = register_all()
        handlers_count = len(registered)
        log.info("[Bootstrap] registered %d handlers: %s", handlers_count, registered)
    except Exception:  # noqa: BLE001
        log.exception("[Bootstrap] handler registration failed")

    return {
        "hydrated": hydrated,
        "default_seeded": seeded,
        "trading_agents_registered": trading,
        "user_agents_registered": user_agents,
        "handlers_registered": handlers_count,
    }


def _register_trading_agents() -> int:
    eng = get_engine()
    if eng is None:
        return 0
    count = 0
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, symbol, category, strategy "
                "FROM trading_agents "
                "WHERE COALESCE(show_in_leaderboard, TRUE) = TRUE"
            )
        ).mappings().all()
    for row in rows:
        agent_id = f"trading-{int(row['id']):04d}"
        if swarm_registry.get_agent(agent_id):
            continue
        caps = ["trading"]
        if row.get("category"):
            caps.append(str(row["category"]).lower())
        if row.get("strategy"):
            caps.append(str(row["strategy"]).lower().replace(" ", "_"))
        if row.get("symbol"):
            caps.append(str(row["symbol"]).upper())
        swarm_registry.register_agent(
            agent_id=agent_id,
            name=row["name"],
            swarm="trading",
            capabilities=caps,
            agent_type="worker",
            priority=5,
            metadata={
                "trading_agent_id": int(row["id"]),
                "symbol": row.get("symbol"),
                "strategy": row.get("strategy"),
                "category": row.get("category"),
                "source": "auto_register",
            },
        )
        count += 1
    return count


def _register_user_agents() -> int:
    eng = get_engine()
    if eng is None:
        return 0
    count = 0
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, symbol, strategy_type, status "
                "FROM user_agents "
                "WHERE status = 'active'"
            )
        ).mappings().all()
    for row in rows:
        agent_id = f"user-{int(row['id']):05d}"
        if swarm_registry.get_agent(agent_id):
            continue
        caps = ["trading", "user_built"]
        if row.get("strategy_type"):
            caps.append(str(row["strategy_type"]).lower())
        if row.get("symbol"):
            caps.append(str(row["symbol"]).upper())
        swarm_registry.register_agent(
            agent_id=agent_id,
            name=row["name"],
            swarm="trading",
            capabilities=caps,
            agent_type="worker",
            priority=4,
            metadata={
                "user_agent_id": int(row["id"]),
                "strategy_type": row.get("strategy_type"),
                "symbol": row.get("symbol"),
                "source": "user_builder",
            },
        )
        count += 1
    return count


# ── Step 4 — Orchestra scheduler (cheap heartbeat thread) ────────────────
class _OrchestraScheduler:
    """Cheap in-process timer that enqueues orchestra_tick periodically.

    Note: Dramatiq has dramatiq-crontab / periodiq plugins for proper
    scheduling, but for our scale a 30s timer in the Flask process is
    sufficient and zero-dependency.
    """

    def __init__(self, interval_seconds: int = 30) -> None:
        self.interval = interval_seconds
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="OrchestraScheduler", daemon=True
        )
        self._thread.start()
        log.info("[Orchestra] scheduler started (interval=%ss)", self.interval)

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        # Lazy import — actor must be importable only when broker is up.
        try:
            try:
                from core.swarm_actors import orchestra_tick
            except ModuleNotFoundError:
                from hermes.core.swarm_actors import orchestra_tick
        except Exception:  # noqa: BLE001
            log.warning("[Orchestra] actor import failed; scheduler will retry", exc_info=True)
            orchestra_tick = None  # type: ignore[assignment]

        while self._running:
            try:
                if orchestra_tick is not None:
                    orchestra_tick.send()
                else:
                    swarm_registry.heartbeat("orchestra-001")
                    swarm_registry.reap_dead()
            except Exception:  # noqa: BLE001
                log.debug("[Orchestra] tick failed", exc_info=True)
            time.sleep(self.interval)


orchestra_scheduler = _OrchestraScheduler(
    interval_seconds=int(os.getenv("HERMES_ORCHESTRA_INTERVAL", "30"))
)


# ── Public entrypoint ─────────────────────────────────────────────────────
def bootstrap_swarm(start_scheduler: bool = True) -> dict[str, int]:
    """Idempotent app-startup hook."""
    global _BOOTSTRAPPED
    with _LOCK:
        if _BOOTSTRAPPED:
            return {"already_bootstrapped": 1}
        try:
            stats = hydrate_and_seed()
        except Exception:  # noqa: BLE001
            log.exception("[Bootstrap] hydrate_and_seed failed")
            stats = {"error": 1}
        if start_scheduler:
            try:
                orchestra_scheduler.start()
            except Exception:  # noqa: BLE001
                log.exception("[Bootstrap] orchestra scheduler failed")
        _BOOTSTRAPPED = True
        log.info("[Bootstrap] swarm v2 ready: %s", stats)
        return stats
