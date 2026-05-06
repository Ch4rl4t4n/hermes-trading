"""No-code agent builder: constants, tier caps, AI summary fallback."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from core.tier_access import (
    TIER_ADMIN,
    TIER_BASIC,
    TIER_ELITE,
    TIER_MEDIUM,
    TIER_PRO,
    effective_tier,
    normalize_tier,
    referral_extra_agent_slots,
)

log = logging.getLogger("agent_builder")

ALLOWED_SYMBOLS = frozenset(
    {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOT", "MATIC", "LINK"}
)
ALLOWED_STRATEGIES = frozenset(
    {
        "momentum",
        "mean_reversion",
        "breakout",
        "trend_following",
        "scalping",
        "grid",
        "dca",
    }
)
STRATEGY_LABELS: dict[str, str] = {
    "momentum": "Momentum",
    "mean_reversion": "Mean Reversion",
    "breakout": "Breakout",
    "trend_following": "Trend Following",
    "scalping": "Scalping",
    "grid": "Grid Trading",
    "dca": "DCA (Dollar Cost Averaging)",
}

ANTHROPIC_MODEL_DEFAULT = "claude-sonnet-4-20250514"


def symbol_to_pair(sym: str) -> str:
    s = (sym or "").strip().upper()
    if "/" in s:
        return s
    return f"{s}/USD"


def user_agent_cap_for_tier(tier: str) -> int | None:
    """Maximum user-created agents (non-deleted). None = unlimited."""
    t = normalize_tier(tier)
    if t in (TIER_ADMIN, TIER_ELITE):
        return None
    if t == TIER_PRO:
        return 5
    if t == TIER_MEDIUM:
        return 3
    if t == TIER_BASIC:
        return 1
    return 1


def user_agent_cap_for_user(user: Any) -> int | None:
    base = user_agent_cap_for_tier(effective_tier(user))
    if base is None:
        return None
    return base + referral_extra_agent_slots(user)


def fallback_ai_summary(payload: dict[str, Any]) -> str:
    """Slovak fallback when Anthropic is unavailable."""
    sym = payload.get("symbol") or "—"
    st = payload.get("strategy_type") or "momentum"
    label = STRATEGY_LABELS.get(str(st), str(st))
    cfg = payload.get("config_json") if isinstance(payload.get("config_json"), dict) else {}
    sl = cfg.get("stop_loss_pct", 2.0)
    ps = cfg.get("position_size_pct", 10.0)
    return (
        f"Tento agent obchoduje {sym} stratégiou „{label}“. "
        f"Risk frame: stop-loss {sl} %, veľkosť pozície {ps} % kapitálu. "
        "Paper trading simuluje signály podľa zvoleného štýlu — sleduj výsledky na dashbordoch Hermes."
    )


def generate_ai_summary_sync(symbol: str, strategy_type: str, config_json: dict[str, Any]) -> str:
    """Call Anthropic; on any failure return fallback (no exception to caller)."""
    payload = {"symbol": symbol, "strategy_type": strategy_type, "config_json": config_json}
    key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        return fallback_ai_summary(payload)
    model = (os.getenv("HERMES_AGENT_BUILDER_MODEL") or ANTHROPIC_MODEL_DEFAULT).strip()
    try:
        import anthropic  # noqa: PLC0415

        client = anthropic.Anthropic(api_key=key)
        user_json = json.dumps(payload, ensure_ascii=False)
        msg = client.messages.create(
            model=model,
            max_tokens=320,
            system=(
                "You are a trading assistant. Generate a brief, exciting 2-3 sentence description "
                "of this trading agent configuration. Be specific about the strategy and parameters. "
                "Respond in the same language the user's platform uses (Slovak)."
            ),
            messages=[{"role": "user", "content": user_json}],
        )
        parts: list[str] = []
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", "") or "")
        text = "".join(parts).strip()
        if text:
            return text
    except Exception:  # noqa: BLE001
        log.exception("Anthropic agent builder summary failed")
    return fallback_ai_summary(payload)
