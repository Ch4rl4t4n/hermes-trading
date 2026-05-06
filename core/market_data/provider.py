"""Abstraction for supplemental quotes (cross-check, LLM, fallback)."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MarketDataProvider(Protocol):
    """Return last price for a symbol or None if unavailable."""

    def last_price(self, symbol: str) -> float | None: ...


def get_yfinance_last(symbol: str) -> float | None:
    """Best-effort last close/price via yfinance (no API key). Crypto: use Alpaca-style symbols."""
    try:
        import yfinance as yf  # type: ignore[import-untyped]
    except ImportError:
        return None
    # Map common Hermes symbols to yfinance tickers
    yf_sym = symbol.replace("/", "-") if "/" in symbol else symbol
    if yf_sym.startswith("BTC"):
        yf_sym = "BTC-USD"
    elif yf_sym.startswith("ETH"):
        yf_sym = "ETH-USD"
    elif yf_sym.startswith("SOL"):
        yf_sym = "SOL-USD"
    try:
        t = yf.Ticker(yf_sym)
        h = t.history(period="5d")
        if h is not None and len(h) > 0:
            return float(h["Close"].iloc[-1])
    except Exception:
        return None
    return None
