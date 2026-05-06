"""
Natural-language strategy description → validated parameter dict (Claude Opus).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from core.llm_insights_util import call_insights_llm_json

load_dotenv()

log = logging.getLogger("strategy_builder")

_BASE = Path(__file__).resolve().parent.parent
_AGENT_DIR = _BASE / "config" / "agents"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def validate_strategy_params(raw: dict[str, Any]) -> dict[str, Any]:
    """Clamp strategy parameters to safe ranges."""
    out: dict[str, Any] = {}
    out["rsi_buy_threshold"] = _clamp(float(raw.get("rsi_buy_threshold", 30)), 5, 45)
    out["rsi_sell_threshold"] = _clamp(float(raw.get("rsi_sell_threshold", 70)), 55, 95)
    out["macd_weight"] = _clamp(float(raw.get("macd_weight", 0.3)), 0.0, 1.0)
    out["atr_multiplier_sl"] = _clamp(float(raw.get("atr_multiplier_sl", 2.0)), 0.5, 5.0)
    out["atr_multiplier_tp"] = _clamp(float(raw.get("atr_multiplier_tp", 3.0)), 0.5, 8.0)
    out["min_confidence"] = _clamp(float(raw.get("min_confidence", 0.6)), 0.3, 0.95)
    out["position_size_pct"] = _clamp(float(raw.get("position_size_pct", 3)), 1, 10)
    mode = str(raw.get("trading_mode", "day_trading")).strip()
    if mode not in ("scalping", "day_trading", "long_term", "full_ai"):
        mode = "day_trading"
    out["trading_mode"] = mode
    syms = raw.get("symbols")
    if isinstance(syms, list):
        out["symbols"] = [str(s) for s in syms][:16]
    else:
        out["symbols"] = []
    return out


async def build_strategy_from_prompt(user_prompt: str) -> dict[str, Any]:
    text = (user_prompt or "").strip()
    if len(text) < 8:
        return {"error": "validation", "message": "Please shorten or expand your strategy description."}

    system = (
        "You convert natural language trading ideas into JSON parameters only. "
        "No markdown. Reply with JSON only."
    )
    user = f"""Convert the user instruction into strategy parameters.

User instruction: "{text}"

Available parameters:
- rsi_buy_threshold (0-100, default 30)
- rsi_sell_threshold (0-100, default 70)
- macd_weight (0-1, default 0.3)
- atr_multiplier_sl (stop loss, default 2.0)
- atr_multiplier_tp (take profit, default 3.0)
- min_confidence (0-1, default 0.6)
- position_size_pct (1-10, default 3)  — percent of portfolio
- trading_mode: scalping | day_trading | long_term | full_ai
- symbols: list of symbols (e.g. ["BTC/USD"])

Return a JSON object with these keys and numeric/string values as appropriate."""

    raw = await asyncio.to_thread(
        call_insights_llm_json,
        system,
        user,
        max_tokens=1024,
        kind="strategy_from_prompt",
    )
    if raw.get("error"):
        return raw
    validated = validate_strategy_params(raw)
    return {"ok": True, "params": validated, "raw_model": raw}


def apply_params_to_agent_yaml(symbol: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    Merge params into config/agents/<symbol>.yaml rule_based + top trading_mode.
    Returns {"ok": true, "path": "..."} or error dict.
    """
    # map symbol to yaml file
    sym = symbol.strip()
    path: Path | None = None
    for p in _AGENT_DIR.glob("*.yaml"):
        try:
            with open(p, encoding="utf-8") as f:
                d = yaml.safe_load(f) or {}
            if d.get("symbol") == sym:
                path = p
                break
        except (OSError, yaml.YAMLError):
            continue
    if path is None:
        return {"error": "not_found", "message": f"No agent YAML found for {sym}"}

    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}

    rule = doc.setdefault("rule_based", {})
    rule["rsi_buy_threshold"] = params.get("rsi_buy_threshold", 30)
    rule["rsi_sell_threshold"] = params.get("rsi_sell_threshold", 70)
    rule["signal_confidence_threshold"] = params.get("min_confidence", 0.6)
    doc["trading_mode"] = params.get("trading_mode", "day_trading")

    risk = doc.setdefault("risk", {})
    mx = float(params.get("position_size_pct", 3)) / 100.0
    risk["max_position_pct"] = min(0.25, max(0.01, mx))

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    log.info("Updated strategy YAML for %s from prompt-builder", sym)
    return {"ok": True, "path": str(path)}
