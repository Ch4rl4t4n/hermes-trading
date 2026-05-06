"""
Upcoming economic events (earnings, FOMC, macro releases) for risk awareness.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("economic_calendar")

STOCK_EARNINGS = ("TSLA", "NVDA", "AMD")

FOMC_2026 = [
    ("2026-01-28", "14:00", "FOMC statement"),
    ("2026-03-18", "14:00", "FOMC statement"),
    ("2026-05-06", "14:00", "FOMC statement"),
    ("2026-06-17", "14:00", "FOMC statement"),
    ("2026-07-29", "14:00", "FOMC statement"),
    ("2026-09-16", "14:00", "FOMC statement"),
    ("2026-11-04", "14:00", "FOMC statement"),
    ("2026-12-16", "14:00", "FOMC statement"),
]


def _cpi_dates_2026() -> list[tuple[str, str]]:
    return [
        ("2026-01-14", "13:30", "US CPI"),
        ("2026-02-11", "13:30", "US CPI"),
        ("2026-03-11", "13:30", "US CPI"),
        ("2026-04-10", "13:30", "US CPI"),
        ("2026-05-13", "13:30", "US CPI"),
        ("2026-06-10", "13:30", "US CPI"),
        ("2026-07-14", "13:30", "US CPI"),
        ("2026-08-12", "13:30", "US CPI"),
        ("2026-09-10", "13:30", "US CPI"),
        ("2026-10-14", "13:30", "US CPI"),
        ("2026-11-12", "13:30", "US CPI"),
        ("2026-12-10", "13:30", "US CPI"),
    ]


def _nfp_dates_2026() -> list[tuple[str, str]]:
    return [
        ("2026-01-09", "13:30", "US Nonfarm Payrolls"),
        ("2026-02-06", "13:30", "US Nonfarm Payrolls"),
        ("2026-03-06", "13:30", "US Nonfarm Payrolls"),
        ("2026-04-03", "13:30", "US Nonfarm Payrolls"),
        ("2026-05-08", "13:30", "US Nonfarm Payrolls"),
        ("2026-06-05", "13:30", "US Nonfarm Payrolls"),
        ("2026-07-10", "13:30", "US Nonfarm Payrolls"),
        ("2026-08-07", "13:30", "US Nonfarm Payrolls"),
        ("2026-09-04", "13:30", "US Nonfarm Payrolls"),
        ("2026-10-02", "13:30", "US Nonfarm Payrolls"),
        ("2026-11-06", "13:30", "US Nonfarm Payrolls"),
        ("2026-12-04", "13:30", "US Nonfarm Payrolls"),
    ]


CRYPTO_EVENTS = [
    ("2026-04-22", "12:00", "Crypto macro week (placeholder)", "medium", ["BTC/USD", "ETH/USD", "SOL/USD"]),
]


def _yf_next_earnings(sym: str) -> str | None:
    try:
        import yfinance as yf

        tk = yf.Ticker(sym)
        cal = tk.calendar
        if cal is None or cal.empty:
            return None
        row = cal.iloc[0]
        d = row.get("Earnings Date")
        if hasattr(d, "date"):
            return d.date().isoformat()
        if isinstance(d, str):
            return d[:10]
    except Exception as exc:
        log.debug("earnings %s: %s", sym, exc)
    return None


def _collect_events_sync(days_ahead: int) -> list[dict[str, Any]]:
    today = date.today()
    end = today + timedelta(days=days_ahead)
    out: list[dict[str, Any]] = []

    def add_row(
        d: str,
        tim: str,
        title: str,
        impact: str,
        symbols: list[str],
        auto: str,
    ) -> None:
        try:
            dt_d = date.fromisoformat(d)
        except ValueError:
            return
        if not (today <= dt_d <= end):
            return
        out.append(
            {
                "date": d,
                "time": tim + " UTC",
                "event": title,
                "impact": impact,
                "affected_symbols": symbols,
                "auto_action": auto,
            }
        )

    for d, t, title in FOMC_2026:
        add_row(d, t, title, "high", ["TSLA", "NVDA", "AMD", "GLD", "USO"], "reduce_position")
    for d, t, title in _cpi_dates_2026():
        add_row(d, t, title, "high", ["TSLA", "NVDA", "AMD", "GLD", "USO"], "reduce_position")
    for d, t, title in _nfp_dates_2026():
        add_row(d, t, title, "high", ["TSLA", "NVDA", "AMD", "GLD", "USO"], "reduce_position")
    for d, t, title, impact, syms in CRYPTO_EVENTS:
        add_row(d, t, title, impact, syms, "none")

    for sym in STOCK_EARNINGS:
        ed = _yf_next_earnings(sym)
        if ed:
            try:
                ed_d = date.fromisoformat(ed)
            except ValueError:
                continue
            if today <= ed_d <= end:
                out.append(
                    {
                        "date": ed,
                        "time": "21:00 UTC",
                        "event": f"{sym} earnings (estimated)",
                        "impact": "high",
                        "affected_symbols": [sym],
                        "auto_action": "pause_trading",
                    }
                )

    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for e in sorted(out, key=lambda x: (x["date"], x["event"])):
        key = (e["date"], e["event"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique


async def get_upcoming_events(days_ahead: int = 7) -> list[dict[str, Any]]:
    """Async wrapper — runs sync collector in a thread (yfinance is blocking)."""
    return await asyncio.to_thread(_collect_events_sync, days_ahead)


def get_trading_constraints() -> dict[str, Any]:
    """
    Policy hints for agents: high-impact macro within 2h → half size; within 30m → pause entries.
    Stock earnings within 24h → pause that symbol's new buys.
    """
    now = datetime.now(timezone.utc)
    size_mult = 1.0
    pause_entries = False
    paused_symbols: set[str] = set()

    events = _collect_events_sync(14)
    for ev in events:
        if ev.get("impact") != "high":
            continue
        d_str = ev.get("date")
        t_raw = str(ev.get("time", "14:00 UTC")).replace(" UTC", "")
        try:
            h, m = [int(x) for x in t_raw.split(":")[:2]]
            evt_dt = datetime(
                int(d_str[:4]),
                int(d_str[5:7]),
                int(d_str[8:10]),
                h,
                m,
                tzinfo=timezone.utc,
            )
        except Exception:
            continue
        delta_sec = (evt_dt - now).total_seconds()
        if delta_sec < 0 or delta_sec > 7200:
            continue
        if delta_sec <= 1800:
            pause_entries = True
        else:
            size_mult = min(size_mult, 0.5)

    for sym in STOCK_EARNINGS:
        dt_s = _yf_next_earnings(sym)
        if not dt_s:
            continue
        try:
            ed = datetime(
                int(dt_s[:4]), int(dt_s[5:7]), int(dt_s[8:10]), 21, 0, tzinfo=timezone.utc
            )
        except Exception:
            continue
        if 0 <= (ed - now).total_seconds() <= 86400:
            paused_symbols.add(sym)

    return {
        "size_mult": size_mult,
        "pause_new_entries": pause_entries,
        "paused_symbols": sorted(paused_symbols),
    }
