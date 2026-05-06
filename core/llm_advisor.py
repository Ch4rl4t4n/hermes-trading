"""
Enhanced LLM Advisor for Hermes Trading Platform
Uses Claude to make intelligent trading decisions based on:
- Rule engine signals (RSI, MACD, ATR)
- External data (Fear&Greed, CoinMarketCap, CoinGecko, News, Yahoo)
- Market regime detection
- Risk parameters

Supports 4 trading modes: scalping, day_trading, long_term, full_ai
"""
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("llm_advisor")

# Model defaults
DEFAULT_HAIKU = "claude-opus-4-7"
DEFAULT_SONNET = "claude-opus-4-7"

# Trading mode configurations
TRADING_MODES = {
    "scalping": {
        "description": "Fast 5m-15m trades, small profits, high frequency",
        "timeframe": "5m-15m",
        "target_profit": "0.5-2%",
        "stop_loss": "0.5-1%",
        "max_hold_time": "1-4 hours",
        "trades_per_day": "10-30",
        "position_size_pct": 0.02,  # 2% of portfolio per trade
        "prompt_style": "aggressive_scalper",
    },
    "day_trading": {
        "description": "Intraday 15m-1h trades, moderate profits",
        "timeframe": "15m-1h",
        "target_profit": "2-5%",
        "stop_loss": "2-3%",
        "max_hold_time": "1-8 hours",
        "trades_per_day": "3-8",
        "position_size_pct": 0.05,  # 5% of portfolio per trade
        "prompt_style": "balanced_daytrader",
    },
    "long_term": {
        "description": "Swing trading 4h-1D, larger moves, fewer trades",
        "timeframe": "4h-1D",
        "target_profit": "5-15%",
        "stop_loss": "5-8%",
        "max_hold_time": "1-14 days",
        "trades_per_day": "0-2",
        "position_size_pct": 0.10,  # 10% of portfolio per trade
        "prompt_style": "patient_swing",
    },
    "full_ai": {
        "description": "LLM-led: wider discretion within risk caps; pair with backtests + API monitoring",
        "timeframe": "15m-1D (context-dependent)",
        "target_profit": "2-12%",
        "stop_loss": "2-6%",
        "max_hold_time": "hours to 1 day",
        "trades_per_day": "2-12",
        "position_size_pct": 0.06,
        "prompt_style": "full_ai_director",
    },
}

# System prompts per trading mode
SYSTEM_PROMPTS = {
    "aggressive_scalper": """You are an expert crypto/stock SCALPER for the Hermes trading platform.

Your job: Analyze the rule engine signal + market data and decide whether to execute the trade.

SCALPING RULES:
- You look for QUICK 0.5-2% moves, in and out fast
- Volume spikes and momentum are your best friends
- Fear & Greed extremes (< 20 or > 80) = stronger signals
- NEWS is critical — breaking news = immediate opportunity
- If RSI is extreme AND volume is high → strong entry
- AVOID trading during low volume periods
- AVOID trading against the macro trend
- Position size: SMALL (2% of portfolio max per trade)

Respond with ONLY a JSON object (no markdown, no explanation):
{"action": "BUY" or "SELL" or "HOLD", "confidence": 0.0-1.0, "reason": "one sentence", "position_size_pct": 0.01-0.05, "stop_loss_pct": 0.5-2.0, "take_profit_pct": 0.5-3.0}""",

    "balanced_daytrader": """You are an expert DAY TRADER for the Hermes trading platform.

Your job: Analyze the rule engine signal + market data and decide whether to execute the trade.

DAY TRADING RULES:
- You look for 2-5% intraday moves
- Combine technical signals (RSI, MACD) with market sentiment
- Fear & Greed Index guides position sizing (extreme fear = bigger positions on buys)
- NEWS sentiment matters — positive news + technical buy = strong signal
- Check market regime: trending markets = follow trend, ranging = mean reversion
- CoinMarketCap dominance shifts signal rotation opportunities
- AVOID overtrading — quality over quantity, max 8 trades per day
- Risk/Reward ratio must be at least 2:1

Respond with ONLY a JSON object (no markdown, no explanation):
{"action": "BUY" or "SELL" or "HOLD", "confidence": 0.0-1.0, "reason": "one sentence", "position_size_pct": 0.02-0.08, "stop_loss_pct": 2.0-4.0, "take_profit_pct": 4.0-10.0}""",

    "patient_swing": """You are an expert SWING TRADER for the Hermes trading platform.

Your job: Analyze the rule engine signal + market data and decide whether to execute the trade.

SWING TRADING RULES:
- You look for 5-15% moves over days to weeks
- MACRO data matters most: Fed rates, CPI, market cap trends
- Fear & Greed extremes are your BEST entry signals (buy at extreme fear, sell at extreme greed)
- News should confirm the technical setup, not drive it
- BTC dominance trends signal crypto rotation
- Yahoo Finance fundamentals matter for stocks (PE ratio, earnings)
- PATIENCE — only trade A+ setups, max 2 trades per day
- Risk/Reward ratio must be at least 3:1
- Use larger position sizes (up to 10%) because setups are higher quality

Respond with ONLY a JSON object (no markdown, no explanation):
{"action": "BUY" or "SELL" or "HOLD", "confidence": 0.0-1.0, "reason": "one sentence", "position_size_pct": 0.05-0.15, "stop_loss_pct": 4.0-8.0, "take_profit_pct": 8.0-20.0}""",

    "full_ai_director": """You are the FULL-AI trading director for the Hermes platform.

Your job: With MAXIMUM analytical depth, decide BUY / SELL / HOLD using the rule signal plus ALL provided market context (regime, sentiment, news, fundamentals). Risk limits are enforced downstream — you focus on edge quality and clear reasoning.

FULL-AI RULES:
- You are not locked to a single timeframe: use the best horizon for THIS setup (quick scalp, intraday, or multi-hour swing) but stay coherent with the detected regime.
- Synthesize contradictions explicitly (e.g. bullish RSI but bearish news).
- When uncertain, HOLD with low confidence rather than force a trade.
- Respect long-only constraints implied by the platform: SELL means exit / reduce long; do not assume shorting.
- Prefer moderate size (about 3-8% of portfolio) unless the regime and confluence are exceptional.
- Cite the top 1-2 drivers in your reason (regime, sentiment, technical, or event).

Monitoring note: decisions are logged with timestamps and exposed via the Hermes API for audit; validate strategy assumptions with historical backtests before expecting live performance.

Respond with ONLY a JSON object (no markdown, no explanation):
{"action": "BUY" or "SELL" or "HOLD", "confidence": 0.0-1.0, "reason": "one sentence", "position_size_pct": 0.03-0.10, "stop_loss_pct": 2.0-6.0, "take_profit_pct": 4.0-14.0}""",
}


@dataclass
class LLMDecision:
    action: str  # BUY, SELL, HOLD
    confidence: float  # 0.0 - 1.0
    reason: str
    position_size_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    raw_response: str = ""


def _model_for_request(use_sonnet: bool) -> str:
    if use_sonnet:
        return os.getenv("HERMES_LLM_SONNET_MODEL", DEFAULT_SONNET)
    return os.getenv("HERMES_LLM_HAIKU_MODEL", DEFAULT_HAIKU)


def parse_llm_response(text: str) -> dict:
    """Extract JSON from LLM response."""
    raw = text.strip()
    # Remove markdown code blocks if present
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)
    # Try to find JSON object
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def build_context_prompt(
    symbol: str,
    asset_type: str,
    rule_signal: dict,
    market_context: dict,
    trading_mode: str = "day_trading",
    current_position: Optional[dict] = None,
    regime: Optional[dict] = None,
) -> str:
    """Build the user prompt with all available data.

    `regime` is an optional dict like
        {"regime": "trending_up", "confidence": 0.8, "details": {...}}
    produced by `core.regime_detector.detect_regime`.  When present we
    surface it prominently so Claude can size/skip accordingly.
    """

    mode_config = TRADING_MODES.get(trading_mode, TRADING_MODES["day_trading"])

    parts = []
    parts.append(f"=== TRADE DECISION REQUEST ===")
    parts.append(f"Symbol: {symbol}")
    parts.append(f"Asset Type: {asset_type}")
    parts.append(f"Trading Mode: {trading_mode.upper()} ({mode_config['description']})")
    parts.append(f"Target: {mode_config['target_profit']} profit, {mode_config['stop_loss']} stop loss")
    parts.append("")

    # Market regime — placed early so it dominates the LLM's framing.
    if regime and isinstance(regime, dict) and regime.get("regime"):
        parts.append("=== MARKET REGIME ===")
        parts.append(f"Regime: {regime['regime']}  (confidence {float(regime.get('confidence', 0)):.2f})")
        details = regime.get("details") or {}
        for k in ("price", "ema20", "ema50", "adx", "atr_ratio", "pct_change_24h"):
            if k in details:
                parts.append(f"{k}: {details[k]}")
        # Regime-specific guidance reminders.
        guidance = {
            "trending_up": "Bias: TREND-FOLLOWING. Prefer BUY pullbacks; avoid fading the trend.",
            "trending_down": "Bias: AVOID LONGS. Strongly prefer HOLD/SELL; only buy on confirmed reversals.",
            "ranging": "Bias: MEAN-REVERSION. Buy near support, sell near resistance, smaller size.",
            "volatile": "Bias: REDUCE SIZE / WIDER STOPS. Only A+ setups, demand R/R ≥ 3:1.",
            "crash": "Bias: NO LONGS. Almost always HOLD or SELL; capital preservation > opportunity.",
            "unknown": "Insufficient data — be conservative; default to HOLD unless overwhelming evidence.",
        }.get(regime["regime"], "")
        if guidance:
            parts.append(f"Guidance: {guidance}")
        parts.append("")

    # Rule engine signal
    parts.append("=== RULE ENGINE SIGNAL ===")
    parts.append(f"Direction: {rule_signal.get('direction', 'HOLD')}")
    parts.append(f"Confidence: {rule_signal.get('confidence', 0):.2f}")
    if rule_signal.get('rsi'):
        parts.append(f"RSI(14): {rule_signal['rsi']:.1f}")
    if rule_signal.get('macd_signal'):
        parts.append(f"MACD Signal: {rule_signal['macd_signal']}")
    if rule_signal.get('price'):
        parts.append(f"Current Price: ${rule_signal['price']:,.2f}")
    parts.append("")

    # Current position
    if current_position:
        parts.append("=== CURRENT POSITION ===")
        parts.append(f"Side: {current_position.get('side', 'none')}")
        parts.append(f"Qty: {current_position.get('qty', 0)}")
        parts.append(f"Entry Price: ${current_position.get('entry_price', 0):,.2f}")
        parts.append(f"Unrealized P&L: {current_position.get('unrealized_pnl_pct', 0):.2f}%")
        parts.append("")

    # Market sentiment
    crypto_fg = market_context.get("crypto_fg", {})
    stocks_fg = market_context.get("stocks_fg", {})
    if crypto_fg or stocks_fg:
        parts.append("=== MARKET SENTIMENT ===")
        if crypto_fg and not crypto_fg.get("error"):
            parts.append(f"Crypto Fear & Greed: {crypto_fg.get('value', '?')}/100 ({crypto_fg.get('label', '?')})")
        if stocks_fg and not stocks_fg.get("error"):
            parts.append(f"Stocks Fear & Greed: {stocks_fg.get('value', '?')}/100 ({stocks_fg.get('label', '?')})")
        parts.append("")

    # CoinMarketCap data
    cmc = market_context.get("cmc_quote", {})
    cmc_global = market_context.get("cmc_global", {})
    if cmc and not cmc.get("error"):
        parts.append("=== COINMARKETCAP ===")
        if cmc.get("price"):
            parts.append(f"CMC Price: ${cmc['price']:,.2f}")
        if cmc.get("change_1h") is not None:
            parts.append(f"Change 1h: {cmc['change_1h']:.2f}%")
        if cmc.get("change_24h") is not None:
            parts.append(f"Change 24h: {cmc['change_24h']:.2f}%")
        if cmc.get("change_7d") is not None:
            parts.append(f"Change 7d: {cmc['change_7d']:.2f}%")
        if cmc.get("volume_24h"):
            parts.append(f"Volume 24h: ${cmc['volume_24h']:,.0f}")
        if cmc.get("market_cap_dominance"):
            parts.append(f"Market Dominance: {cmc['market_cap_dominance']:.1f}%")
        parts.append("")

    if cmc_global and not cmc_global.get("error"):
        parts.append("=== GLOBAL CRYPTO MARKET ===")
        if cmc_global.get("total_market_cap"):
            parts.append(f"Total Market Cap: ${cmc_global['total_market_cap']/1e9:,.1f}B")
        if cmc_global.get("btc_dominance"):
            parts.append(f"BTC Dominance: {cmc_global['btc_dominance']:.1f}%")
        parts.append("")

    # CoinGecko data
    cg = market_context.get("coingecko", {})
    if cg and not cg.get("error"):
        parts.append("=== COINGECKO ===")
        if cg.get("volume_24h"):
            parts.append(f"Volume 24h: ${cg['volume_24h']:,.0f}")
        if cg.get("change_24h"):
            parts.append(f"Change 24h: {cg['change_24h']:.2f}%")
        if cg.get("change_7d"):
            parts.append(f"Change 7d: {cg['change_7d']:.2f}%")
        parts.append("")

    # Yahoo Finance data
    yf = market_context.get("yahoo", {})
    if yf and not yf.get("error"):
        parts.append("=== YAHOO FINANCE ===")
        if yf.get("pe_ratio"):
            parts.append(f"P/E Ratio: {yf['pe_ratio']:.1f}")
        if yf.get("recommendation"):
            parts.append(f"Analyst Recommendation: {yf['recommendation']}")
        if yf.get("52w_high"):
            parts.append(f"52W High: ${yf['52w_high']:,.2f}")
        if yf.get("52w_low"):
            parts.append(f"52W Low: ${yf['52w_low']:,.2f}")
        parts.append("")

    # News
    news = market_context.get("news", [])
    if news:
        parts.append("=== RECENT NEWS ===")
        for i, article in enumerate(news[:3]):  # Max 3 articles
            parts.append(f"{i+1}. [{article.get('source', '?')}] {article.get('headline', '?')}")
            if article.get("summary"):
                parts.append(f"   {article['summary'][:150]}")
        parts.append("")

    # FRED macro data
    fred = market_context.get("fred", {})
    if fred and not fred.get("error"):
        parts.append("=== MACRO DATA (FRED) ===")
        for key, val in fred.items():
            if isinstance(val, dict) and val.get("value"):
                parts.append(f"{key}: {val['value']} (as of {val.get('date', '?')})")
        parts.append("")

    parts.append("=== YOUR DECISION ===")
    parts.append("Based on ALL the above data, should we execute this trade?")
    parts.append("Consider: signal quality, market sentiment, news, risk/reward ratio.")
    parts.append("Respond with ONLY a JSON object.")

    return "\n".join(parts)


async def get_llm_decision(
    symbol: str,
    asset_type: str,
    rule_signal: dict,
    market_context: dict,
    trading_mode: str = "day_trading",
    current_position: Optional[dict] = None,
    use_sonnet: bool = False,
    regime: Optional[dict] = None,
) -> LLMDecision:
    """
    Ask Claude for a trading decision based on all available data.

    Args:
        symbol: Trading pair (e.g., "BTC/USD")
        asset_type: "crypto", "stock", or "commodity_etf"
        rule_signal: Dict with direction, confidence, rsi, macd_signal, price
        market_context: Dict from external_data.get_market_context()
        trading_mode: "scalping", "day_trading", "long_term", or "full_ai"
        current_position: Optional current position info
        use_sonnet: Use Sonnet instead of Haiku for important decisions

    Returns:
        LLMDecision with action, confidence, reason, sizing
    """
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set")
        return LLMDecision(
            action="HOLD",
            confidence=0.0,
            reason="API key not configured",
            position_size_pct=0.0,
            stop_loss_pct=0.0,
            take_profit_pct=0.0,
        )

    model = _model_for_request(use_sonnet)
    mode_config = TRADING_MODES.get(trading_mode, TRADING_MODES["day_trading"])
    system_prompt = SYSTEM_PROMPTS.get(mode_config["prompt_style"], SYSTEM_PROMPTS["balanced_daytrader"])
    user_prompt = build_context_prompt(
        symbol, asset_type, rule_signal, market_context, trading_mode,
        current_position, regime=regime,
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        t0 = time.time()

        response = client.messages.create(
            model=model,
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        elapsed = time.time() - t0
        raw_text = response.content[0].text if response.content else ""

        log.info("LLM %s responded in %.1fs (model=%s)", symbol, elapsed, model)

        parsed = parse_llm_response(raw_text)

        if not parsed or "action" not in parsed:
            log.warning("LLM %s: could not parse response: %s", symbol, raw_text[:200])
            return LLMDecision(
                action="HOLD",
                confidence=0.0,
                reason="Could not parse LLM response",
                position_size_pct=0.0,
                stop_loss_pct=0.0,
                take_profit_pct=0.0,
                raw_response=raw_text,
            )

        action = parsed.get("action", "HOLD").upper()
        if action not in ("BUY", "SELL", "HOLD"):
            action = "HOLD"

        decision = LLMDecision(
            action=action,
            confidence=min(1.0, max(0.0, float(parsed.get("confidence", 0.5)))),
            reason=parsed.get("reason", "No reason given"),
            position_size_pct=min(0.20, max(0.01, float(parsed.get("position_size_pct", mode_config["position_size_pct"])))),
            stop_loss_pct=float(parsed.get("stop_loss_pct", 3.0)),
            take_profit_pct=float(parsed.get("take_profit_pct", 6.0)),
            raw_response=raw_text,
        )

        log.info(
            "LLM %s decision: %s (conf=%.2f, size=%.1f%%, SL=%.1f%%, TP=%.1f%%) — %s",
            symbol, decision.action, decision.confidence,
            decision.position_size_pct * 100, decision.stop_loss_pct,
            decision.take_profit_pct, decision.reason,
        )

        return decision

    except Exception as e:
        log.error("LLM %s error: %s", symbol, e)
        return LLMDecision(
            action="HOLD",
            confidence=0.0,
            reason=f"LLM error: {str(e)}",
            position_size_pct=0.0,
            stop_loss_pct=0.0,
            take_profit_pct=0.0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatible wrapper used by agents/base_agent.py
#
# BaseAgent._apply_llm_if_enabled() expects:
#     advisor = get_llm_advisor()
#     advisor.is_configured()                          -> bool
#     await advisor.review_signal(agent, signal)       -> (SignalResult, meta)
#
# The class below adapts the new async get_llm_decision() pipeline + the
# external_data.get_market_context() data source to that legacy interface.
# ─────────────────────────────────────────────────────────────────────────────


class LLMAdvisor:
    """
    Adapter that lets the existing rule-engine agent loop drive the new LLM
    decision pipeline (get_llm_decision + external_data) without changes.
    """

    def is_configured(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())

    async def review_signal(self, agent: Any, signal: Any) -> tuple[Any, dict]:
        """
        Take the agent's rule-based SignalResult, enrich it with external market
        context, ask Claude for a final BUY/SELL/HOLD, and return a new
        SignalResult plus a meta dict (model, usage, skipped, error).
        """
        # Imported lazily to avoid a circular import at module load time.
        from agents.base_agent import SignalResult
        from core.external_data import get_market_context

        cfg = agent.cfg
        symbol = agent.symbol
        agent_asset_type = cfg.asset_type   # crypto | stock | commodity_etf

        # external_data only branches on "crypto" vs everything-else (stock-like)
        ext_asset_type = "crypto" if agent_asset_type == "crypto" else "stock"

        trading_mode = getattr(cfg, "trading_mode", "day_trading")
        use_sonnet = signal.confidence >= getattr(cfg, "llm_use_sonnet_above", 1.1)
        model_name = _model_for_request(use_sonnet)

        # Build the rule_signal payload that get_llm_decision expects.
        try:
            _, _, macd_hist = agent.calculate_macd()
        except Exception:
            macd_hist = 0.0
        if macd_hist > 0:
            macd_signal_str = "bullish_crossover"
        elif macd_hist < 0:
            macd_signal_str = "bearish_crossover"
        else:
            macd_signal_str = "neutral"

        try:
            rsi_val = agent.calculate_rsi()
        except Exception:
            rsi_val = 50.0

        price_now = agent.prices[-1] if getattr(agent, "prices", None) else 0.0

        rule_signal = {
            "direction": signal.direction,
            "confidence": float(signal.confidence),
            "rsi": float(rsi_val),
            "macd_signal": macd_signal_str,
            "price": float(price_now),
        }

        # Optional current position context for the LLM prompt.
        current_position = None
        if getattr(agent, "position_qty", 0) > 0 and getattr(agent, "entry_price", None):
            entry = agent.entry_price
            cur = price_now or entry
            pnl_pct = ((cur - entry) / entry * 100.0) if entry else 0.0
            current_position = {
                "side": "LONG",
                "qty": agent.position_qty,
                "entry_price": entry,
                "unrealized_pnl_pct": pnl_pct,
            }

        # Reuse the agent-level cached market context if available — saves
        # a second round-trip every tick.  Falls back to a fresh fetch.
        market_context: dict
        cached = getattr(agent, "_cached_market_context", None)
        if cached:
            market_context = cached
        else:
            try:
                market_context = await get_market_context(symbol, ext_asset_type)
            except Exception as exc:
                log.warning("external_data fetch failed for %s: %s", symbol, exc)
                return signal, {
                    "model": model_name,
                    "usage": {},
                    "skipped": False,
                    "error": f"market_context: {exc}",
                }

        # Pull the regime detected by the agent's tick (if any) and forward it.
        regime_payload = None
        if getattr(agent, "last_regime", None) and agent.last_regime != "unknown":
            regime_payload = {
                "regime": agent.last_regime,
                "confidence": getattr(agent, "last_regime_details", {}).get("confidence", 0.5),
                "details": getattr(agent, "last_regime_details", {}),
            }

        # Delegate to the new decision function.
        try:
            decision = await get_llm_decision(
                symbol=symbol,
                asset_type=agent_asset_type,
                rule_signal=rule_signal,
                market_context=market_context,
                trading_mode=trading_mode,
                current_position=current_position,
                use_sonnet=use_sonnet,
                regime=regime_payload,
            )
        except Exception as exc:
            log.warning("get_llm_decision failed for %s: %s", symbol, exc)
            return signal, {
                "model": model_name,
                "usage": {},
                "skipped": False,
                "error": f"llm_decision: {exc}",
            }

        # Surface the full LLMDecision back to the agent so calculate_qty can
        # honour Claude's position_size_pct / stop / target.
        try:
            agent.last_llm_decision = decision
        except Exception:
            pass

        new_signal = SignalResult(
            direction=decision.action,
            confidence=float(decision.confidence),
            reason=f"[LLM {trading_mode}] {decision.reason}",
            position_size_pct=decision.position_size_pct,
            stop_loss_pct=decision.stop_loss_pct,
            take_profit_pct=decision.take_profit_pct,
        )
        meta = {
            "model": model_name,
            # get_llm_decision does not currently surface token counts; placeholder
            # keeps the audit log shape stable.
            "usage": {},
            "skipped": False,
            "error": None,
            "regime": regime_payload.get("regime") if regime_payload else None,
        }
        return new_signal, meta


# Module-level singleton (matches the legacy convention).
_advisor: Optional[LLMAdvisor] = None


def get_llm_advisor() -> LLMAdvisor:
    """Return a process-wide LLMAdvisor singleton."""
    global _advisor
    if _advisor is None:
        _advisor = LLMAdvisor()
    return _advisor


# Legacy alias so existing tests / callers can `from core.llm_advisor import
# parse_llm_action_json` without breaking.
parse_llm_action_json = parse_llm_response


# ── Quick test ──
if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)

    async def test():
        from core.external_data import get_market_context

        print("=== Fetching market context for BTC/USD ===\n")
        ctx = await get_market_context("BTC/USD", "crypto")

        print("=== Asking Claude for trading decision ===\n")

        rule_signal = {
            "direction": "BUY",
            "confidence": 0.72,
            "rsi": 35.0,
            "macd_signal": "bullish_crossover",
            "price": 78444.0,
        }

        # Test all 3 modes
        for mode in ["scalping", "day_trading", "long_term", "full_ai"]:
            print(f"\n--- Mode: {mode.upper()} ---")
            decision = await get_llm_decision(
                symbol="BTC/USD",
                asset_type="crypto",
                rule_signal=rule_signal,
                market_context=ctx,
                trading_mode=mode,
            )
            print(f"Action: {decision.action}")
            print(f"Confidence: {decision.confidence:.2f}")
            print(f"Position Size: {decision.position_size_pct*100:.1f}%")
            print(f"Stop Loss: {decision.stop_loss_pct:.1f}%")
            print(f"Take Profit: {decision.take_profit_pct:.1f}%")
            print(f"Reason: {decision.reason}")
            print()

    asyncio.run(test())
