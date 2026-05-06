"""
Daily AI market briefing (08:00 UTC schedule from hermes.py).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("daily_summary")

_BASE = Path(__file__).resolve().parent.parent
_SUM_DIR = _BASE / "logs" / "daily_summaries"
_PERF_PATH = Path(os.getenv("HERMES_BASE", str(_BASE))) / "logs" / "performance.json"


def _yesterday_trades() -> list[dict[str, Any]]:
    if not _PERF_PATH.exists():
        return []
    try:
        with open(_PERF_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        trades = raw.get("trades") or []
    except (OSError, json.JSONDecodeError):
        return []
    y = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    out = []
    for t in trades:
        ex = t.get("exit_ts") or ""
        try:
            d = datetime.fromisoformat(ex.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if d == y:
            out.append(
                {
                    "symbol": t.get("symbol"),
                    "pnl_usd": t.get("pnl_usd"),
                    "pnl_pct": t.get("pnl_pct"),
                    "mode": t.get("mode"),
                    "regime": t.get("regime"),
                }
            )
    return out[-50:]


def _save_summary(for_date: date, payload: dict[str, Any]) -> Path:
    _SUM_DIR.mkdir(parents=True, exist_ok=True)
    p = _SUM_DIR / f"{for_date.isoformat()}.json"
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, p)
    return p


def _notify_discord(text: str) -> None:
    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        import requests

        requests.post(url, json={"content": text[:1900]}, timeout=15)
    except Exception as exc:
        log.debug("discord notify: %s", exc)


async def generate_daily_summary(*, force_refresh: bool = False) -> dict[str, Any]:
    """
    Build morning briefing; reuse today's JSON file for 24h unless force_refresh.
    """
    from core.config_loader import load_all_agents
    from core.llm_insights_util import call_insights_llm_json
    from core.external_data import get_cmc_global_metrics, get_crypto_fear_greed
    from core.market_explainer import _fetch_24h_bars_sync
    from core.regime_detector import detect_regime

    today_utc = datetime.now(timezone.utc).date()
    path = _SUM_DIR / f"{today_utc.isoformat()}.json"
    if not force_refresh and path.exists():
        if time.time() - path.stat().st_mtime < 86400:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                return {k: v for k, v in data.items() if not str(k).startswith("_")}
            except (OSError, json.JSONDecodeError):
                pass

    configs = load_all_agents(_BASE / "config" / "agents")
    per_sym: list[dict[str, Any]] = []

    for cfg in configs:
        try:
            bars = await asyncio.to_thread(_fetch_24h_bars_sync, cfg.symbol, cfg.asset_type)
            closes = [b["c"] for b in bars][-60:]
            last = closes[-1] if closes else 0.0
            first = closes[0] if closes else last
            chg = ((last - first) / first * 100) if first else 0.0
            reg = await detect_regime(cfg.symbol, cfg.asset_type, closes, None)
            per_sym.append(
                {
                    "symbol": cfg.symbol,
                    "asset_type": cfg.asset_type,
                    "price": last,
                    "change_24h_pct_approx": round(chg, 2),
                    "regime": reg.regime,
                    "trading_mode": cfg.trading_mode,
                }
            )
        except Exception as exc:
            log.warning("daily summary data %s: %s", cfg.symbol, exc)
            per_sym.append(
                {"symbol": cfg.symbol, "error": str(exc), "trading_mode": cfg.trading_mode}
            )

    global_d: dict[str, Any] = {}
    try:
        global_d["crypto_fear_greed"] = await get_crypto_fear_greed()
        global_d["cmc_global"] = await get_cmc_global_metrics()
    except Exception as exc:
        global_d["error"] = str(exc)

    ytr = _yesterday_trades()
    system = (
        "You are a senior market analyst at a hedge fund. "
        "Reply ONLY with valid JSON, no markdown. "
        "All narrative text fields must be in English."
    )
    user = f"""Create a morning briefing for {today_utc.isoformat()} (UTC).

Per-symbol portfolio data (JSON): {json.dumps(per_sym, ensure_ascii=False, default=str)}
Global context (JSON): {json.dumps(global_d, ensure_ascii=False, default=str)}
Yesterday's closed trades (JSON): {json.dumps(ytr, ensure_ascii=False, default=str)}

Reply ONLY in this JSON shape:
{{
  "date": "{today_utc.isoformat()}",
  "market_mood": "bullish/bearish/neutral/mixed",
  "headline": "One-line headline in English",
  "summary": "Brief market overview — 3 to 5 short paragraphs in English.",
  "per_symbol": {{
    "BTC/USD": {{
      "outlook": "bullish/bearish/neutral",
      "key_levels": [78000, 82000],
      "recommendation": "hold"
    }}
  }},
  "risks": ["risk1", "risk2"],
  "opportunities": ["opportunity1", "opportunity2"]
}}

per_symbol must include a key for every symbol from the input (exact string keys)."""

    parsed = await asyncio.to_thread(
        call_insights_llm_json,
        system,
        user,
        max_tokens=8192,
        kind="daily_summary",
    )
    if parsed.get("error"):
        return {
            "error": parsed.get("error"),
            "message": parsed.get("message", "Generation failed"),
            "partial_context": {"symbols": per_sym, "global": global_d},
        }

    payload = {
        "generated": True,
        "date": parsed.get("date", today_utc.isoformat()),
        "market_mood": parsed.get("market_mood", "neutral"),
        "headline": parsed.get("headline", ""),
        "summary": parsed.get("summary", ""),
        "per_symbol": parsed.get("per_symbol") or {},
        "risks": parsed.get("risks") or [],
        "opportunities": parsed.get("opportunities") or [],
    }
    _save_summary(today_utc, payload)

    try:
        from notifications import telegram

        headline = payload.get("headline", "Hermes briefing")
        telegram.send(f"📊 <b>Daily summary</b>\n{headline}")
    except Exception as exc:
        log.debug("telegram: %s", exc)

    _notify_discord(f"**Daily summary** {today_utc}\n{payload.get('headline', '')}")

    return payload
