# Supplemental market data (Phase 7)

**Primary:** Hermes price history and trading use **Alpaca** (`DataFeed`, `BaseAgent`).

**Abstraction:** `core/market_data/provider.py` defines `MarketDataProvider` and `get_yfinance_last(symbol)`.

- **yfinance** (optional, `pip install yfinance`) — no API key; use for ad-hoc cross-checks or future LLM/sentiment pipelines, not for sub-second trading decisions.
- **Rate limits:** respect Yahoo and provider ToS; cache aggressively.
- **Next steps:** implement `class FinnhubProvider` etc., then compose behind a `CompositeProvider` (Alpaca first, yfinance for gaps).

Do not log API keys. Keep keys in `.env` only.
