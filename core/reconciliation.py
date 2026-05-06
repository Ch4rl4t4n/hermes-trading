"""Compare Alpaca open positions with agent internal state at startup."""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

log = logging.getLogger("hermes.reconcile")

if TYPE_CHECKING:
    from agents.base_agent import BaseAgent


def _candidate_keys(symbol: str) -> set[str]:
    s = symbol.strip()
    return {s, s.replace("/", ""), s.replace("/", "-")}


def reconcile_agent_positions(agents: list["BaseAgent"]) -> list[str]:
    """Log warnings for mismatches; returns list of warning messages."""
    from alpaca.trading.client import TradingClient

    warnings: list[str] = []
    try:
        client = TradingClient(
            os.getenv("ALPACA_API_KEY"),
            os.getenv("ALPACA_API_SECRET"),
            paper=os.getenv("ALPACA_PAPER", "true").lower() == "true",
        )
        positions = client.get_all_positions()
    except Exception as exc:
        msg = f"reconciliation skipped (API): {exc}"
        log.warning(msg)
        return [msg]

    by_sym = {p.symbol: float(p.qty) for p in positions}
    for a in agents:
        qty_broker = 0.0
        for k in _candidate_keys(a.symbol):
            if k in by_sym:
                qty_broker = by_sym[k]
                break
        q = a.position_qty
        if abs(qty_broker - q) > 1e-6 and (qty_broker > 0 or q > 0):
            w = (
                f"{a.name} ({a.symbol}): agent_qty={q:.6f} vs Alpaca_qty={qty_broker:.6f}"
            )
            log.warning("RECONCILE %s", w)
            warnings.append(w)
    if not warnings:
        log.info("Position reconciliation: agent state matches Alpaca (or both flat).")
    else:
        from notifications import telegram
        body = "\n".join(f"• {w}" for w in warnings)
        try:
            telegram.send(f"⚠️ <b>Reconciliation</b>\n{body[:3500]}")
        except Exception:
            pass
    return warnings
