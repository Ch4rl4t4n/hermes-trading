"""Unit tests for DataFeed — no API keys needed (uses mocked clients)."""
import sys
from collections import deque
from datetime import time as dtime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_feed import DataFeed, SymbolMeta


def make_meta(symbol: str, asset_type: str = "crypto",
              tz: str = "UTC",
              start: dtime = dtime(0, 0),
              end: dtime = dtime(23, 59)) -> SymbolMeta:
    return SymbolMeta(symbol=symbol, asset_type=asset_type,
                      timezone=tz, active_hours_start=start, active_hours_end=end)


def make_feed(*metas: SymbolMeta) -> DataFeed:
    with patch("core.data_feed.StockHistoricalDataClient"), \
         patch("core.data_feed.CryptoHistoricalDataClient"):
        return DataFeed(list(metas))


# ── Market hours ───────────────────────────────────────────────────────────────

def test_crypto_always_open():
    feed = make_feed(make_meta("BTC/USD", "crypto", "UTC", dtime(0, 0), dtime(23, 59)))
    assert feed.is_market_open_for("BTC/USD") is True


def test_unknown_symbol_not_open():
    feed = make_feed(make_meta("BTC/USD"))
    assert feed.is_market_open_for("UNKNOWN") is False


def test_ny_market_hours_class():
    # Just verify the timezone ZoneInfo doesn't raise
    feed = make_feed(make_meta("SPY", "stock", "America/New_York", dtime(9, 30), dtime(16, 0)))
    result = feed.is_market_open_for("SPY")
    assert isinstance(result, bool)


# ── Price recording ────────────────────────────────────────────────────────────

def test_record_stores_price():
    feed = make_feed(make_meta("BTC/USD"))
    feed._record("BTC/USD", 93000.0)
    assert feed.get_price("BTC/USD") == 93000.0
    assert 93000.0 in feed.get_history("BTC/USD")


def test_record_updates_history():
    feed = make_feed(make_meta("BTC/USD"))
    for p in [100.0, 101.0, 102.0]:
        feed._record("BTC/USD", p)
    history = feed.get_history("BTC/USD")
    assert history == [100.0, 101.0, 102.0]


def test_rolling_window_limit():
    from core.data_feed import ROLLING_WINDOW
    feed = make_feed(make_meta("BTC/USD"))
    for i in range(ROLLING_WINDOW + 10):
        feed._record("BTC/USD", float(i))
    assert len(feed.get_history("BTC/USD")) == ROLLING_WINDOW


def test_get_price_returns_zero_when_unknown():
    feed = make_feed(make_meta("BTC/USD"))
    assert feed.get_price("UNKNOWN") == 0.0


def test_get_history_returns_empty_when_no_data():
    feed = make_feed(make_meta("BTC/USD"))
    assert feed.get_history("BTC/USD") == []


# ── Symbol classification ──────────────────────────────────────────────────────

def test_crypto_symbols_separated():
    feed = make_feed(
        make_meta("BTC/USD", "crypto"),
        make_meta("ETH/USD", "crypto"),
        make_meta("SPY", "stock"),
    )
    assert set(feed._crypto_symbols()) == {"BTC/USD", "ETH/USD"}
    assert feed._stock_symbols() == ["SPY"]


def test_stock_and_etf_both_go_to_stock_client():
    feed = make_feed(
        make_meta("SPY", "stock"),
        make_meta("GLD", "commodity_etf"),
    )
    # Both should appear in stock symbols (non-crypto)
    assert "SPY" in feed._stock_symbols()
    assert "GLD" in feed._stock_symbols()
    assert len(feed._crypto_symbols()) == 0


if __name__ == "__main__":
    tests = [
        test_crypto_always_open,
        test_unknown_symbol_not_open,
        test_ny_market_hours_class,
        test_record_stores_price,
        test_record_updates_history,
        test_rolling_window_limit,
        test_get_price_returns_zero_when_unknown,
        test_get_history_returns_empty_when_no_data,
        test_crypto_symbols_separated,
        test_stock_and_etf_both_go_to_stock_client,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} tests passed")
