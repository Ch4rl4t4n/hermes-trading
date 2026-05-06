"""Optional supplemental market data (Phase 7). Primary feed remains Alpaca DataFeed."""

from core.market_data.provider import MarketDataProvider, get_yfinance_last

__all__ = ["MarketDataProvider", "get_yfinance_last"]
