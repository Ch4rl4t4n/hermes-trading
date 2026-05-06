"""
Quick smoke test — verifies Alpaca API connectivity and correct price fetching.
Run: /root/hermes/venv/bin/python tests/smoke_test.py
Requires: ALPACA_API_KEY and ALPACA_API_SECRET in .env
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import os

if not os.getenv("ALPACA_API_KEY"):
    print("ERROR: ALPACA_API_KEY not set in .env — fill in your keys first")
    sys.exit(1)

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, CryptoLatestQuoteRequest, StockLatestTradeRequest

trading = TradingClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_API_SECRET"),
    paper=True,
)
stock_data = StockHistoricalDataClient(
    api_key=os.getenv("ALPACA_API_KEY"),
    secret_key=os.getenv("ALPACA_API_SECRET"),
)
crypto_data = CryptoHistoricalDataClient()

print("=" * 55)
print("Hermes Smoke Test — Alpaca Paper Trading")
print("=" * 55)

# Portfolio
account = trading.get_account()
print(f"\nPortfolio: ${float(account.portfolio_value):,.2f}")
print(f"Cash:      ${float(account.cash):,.2f}")
print(f"Status:    {account.status}")

# Stock prices
print("\n--- Stock prices (must NOT be $100.0) ---")
for symbol in ["SPY", "TSLA", "NVDA", "GLD", "SLV", "USO"]:
    try:
        q = stock_data.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))
        price = float(q[symbol].ask_price)
        source = "quote"
        if price == 0.0:
            t = stock_data.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
            price = float(t[symbol].price)
            source = "trade"
        status = "OK" if price > 0 else "FAIL"
        print(f"  [{status}] {symbol:6} ${price:,.2f}  (via {source})")
    except Exception as e:
        print(f"  [ERR] {symbol:6} {e}")

# Crypto prices
print("\n--- Crypto prices ---")
for symbol in ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "LINK/USD"]:
    try:
        q = crypto_data.get_crypto_latest_quote(CryptoLatestQuoteRequest(symbol_or_symbols=symbol))
        price = float(q[symbol].ask_price)
        status = "OK" if price > 0 else "FAIL"
        print(f"  [{status}] {symbol:10} ${price:,.4f}")
    except Exception as e:
        print(f"  [ERR] {symbol:10} {e}")

print("\nSmoke test complete.")
