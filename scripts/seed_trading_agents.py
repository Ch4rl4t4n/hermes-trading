#!/usr/bin/env python3
"""Idempotent seed of trading_agents for marketplace (50 rows)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BASE))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(_BASE / ".env")

ROWS: list[tuple] = [
    ("btc_momentum", "BTC Momentum Hunter", "Rides BTC trends using RSI+MACD", "BTC/USD", "crypto", "momentum", "1h", "medium", "basic", True, 67.3, 1240),
    ("eth_dca", "ETH Dollar Cost Average", "Buys ETH on dips systematically", "ETH/USD", "crypto", "dca", "4h", "low", "basic", True, 72.1, 890),
    ("sol_swing", "SOL Swing Trader", "Captures SOL swing moves", "SOL/USD", "crypto", "swing", "4h", "medium", "basic", True, 61.8, 445),
    ("xrp_breakout", "XRP Breakout Catcher", "Trades XRP breakouts", "XRP/USD", "crypto", "breakout", "1h", "high", "basic", True, 58.9, 678),
    ("doge_sentiment", "DOGE Sentiment Rider", "Trades DOGE on social signals", "DOGE/USD", "crypto", "sentiment", "1h", "high", "basic", True, 55.2, 334),
    ("ada_value", "ADA Value Investor", "Long-term ADA accumulation", "ADA/USD", "crypto", "dca", "1d", "low", "basic", True, 69.4, 212),
    ("avax_momentum", "AVAX Momentum", "AVAX trend following", "AVAX/USD", "crypto", "momentum", "1h", "medium", "basic", True, 63.7, 389),
    ("dot_swing", "DOT Swing", "Polkadot swing trading", "DOT/USD", "crypto", "swing", "4h", "medium", "basic", True, 60.1, 267),
    ("matic_scalp", "MATIC Scalper", "Fast MATIC scalping", "MATIC/USD", "crypto", "scalp", "15m", "high", "basic", True, 57.8, 1567),
    ("shib_momentum", "SHIB Momentum", "SHIB momentum plays", "SHIB/USD", "crypto", "momentum", "1h", "high", "basic", True, 53.4, 445),
    ("ltc_dca", "LTC DCA", "Litecoin accumulation", "LTC/USD", "crypto", "dca", "4h", "low", "medium", True, 70.2, 334),
    ("link_momentum", "LINK Momentum", "Chainlink trend trader", "LINK/USD", "crypto", "momentum", "1h", "medium", "medium", True, 65.3, 489),
    ("uni_swing", "UNI Swing", "Uniswap swing trader", "UNI/USD", "crypto", "swing", "4h", "medium", "medium", True, 62.1, 234),
    ("near_breakout", "NEAR Breakout", "NEAR Protocol breakouts", "NEAR/USD", "crypto", "breakout", "1h", "high", "medium", True, 59.8, 312),
    ("atom_dca", "ATOM DCA", "Cosmos accumulation", "ATOM/USD", "crypto", "dca", "1d", "low", "medium", True, 71.5, 189),
    ("aapl_momentum", "AAPL Momentum", "Apple trend follower", "AAPL", "stock", "momentum", "1h", "low", "basic", True, 73.2, 567),
    ("msft_value", "MSFT Value", "Microsoft value plays", "MSFT", "stock", "swing", "4h", "low", "basic", True, 74.8, 445),
    ("nvda_momentum", "NVDA Momentum", "NVIDIA AI momentum", "NVDA", "stock", "momentum", "1h", "medium", "basic", True, 69.7, 678),
    ("googl_swing", "GOOGL Swing", "Alphabet swing trader", "GOOGL", "stock", "swing", "4h", "low", "basic", True, 71.3, 389),
    ("tsla_swing", "TSLA Swing Trader", "Tesla volatility plays", "TSLA", "stock", "swing", "4h", "high", "basic", True, 62.4, 789),
    ("meta_momentum", "META Momentum", "Meta trend trader", "META", "stock", "momentum", "1h", "medium", "basic", True, 68.9, 512),
    ("amzn_breakout", "AMZN Breakout", "Amazon breakout trader", "AMZN", "stock", "breakout", "4h", "medium", "basic", True, 67.1, 434),
    ("amd_momentum", "AMD Momentum", "AMD chip momentum", "AMD", "stock", "momentum", "1h", "medium", "medium", True, 66.8, 556),
    ("coin_swing", "COIN Swing", "Coinbase swing trader", "COIN", "stock", "swing", "4h", "high", "medium", True, 61.2, 345),
    ("pltr_momentum", "PLTR Momentum", "Palantir momentum", "PLTR", "stock", "momentum", "1h", "medium", "medium", True, 64.5, 423),
    ("mstr_btc", "MSTR BTC Proxy", "MicroStrategy BTC proxy", "MSTR", "stock", "momentum", "1h", "high", "medium", True, 65.8, 312),
    ("nvda_ai", "NVDA AI Surge", "NVIDIA AI news trader", "NVDA", "stock", "sentiment", "1h", "high", "pro", True, 70.1, 234),
    ("shop_growth", "SHOP Growth", "Shopify growth trader", "SHOP", "stock", "swing", "4h", "medium", "pro", True, 63.7, 289),
    ("gold_safe", "Gold Safe Haven", "Gold crisis hedge", "GC=F", "commodity", "hedge", "4h", "low", "basic", True, 75.6, 678),
    ("silver_momentum", "Silver Momentum", "Silver breakout trader", "SI=F", "commodity", "momentum", "1h", "medium", "basic", True, 67.3, 445),
    ("oil_wti", "WTI Oil Trader", "Crude oil trend trader", "CL=F", "commodity", "momentum", "1h", "high", "basic", True, 63.2, 567),
    ("natgas_swing", "Natural Gas Swing", "Gas seasonal trader", "NG=F", "commodity", "seasonal", "1d", "high", "medium", True, 61.8, 334),
    ("copper_momentum", "Copper Momentum", "Copper industrial trader", "HG=F", "commodity", "momentum", "4h", "medium", "medium", True, 64.5, 289),
    ("wheat_seasonal", "Wheat Seasonal", "Wheat harvest cycles", "ZW=F", "commodity", "seasonal", "1d", "medium", "medium", True, 68.9, 212),
    ("gold_hedge", "Gold Inflation Hedge", "Gold vs inflation", "GLD", "commodity", "hedge", "1d", "low", "basic", True, 76.2, 534),
    ("oil_etf", "Oil ETF Trader", "USO trend trader", "USO", "commodity", "momentum", "4h", "medium", "basic", True, 62.1, 423),
    ("spy_index", "SPY Index Trend", "Broad US equities exposure", "SPY", "stock", "momentum", "4h", "medium", "basic", True, 71.0, 1205),
    ("qqq_tech", "QQQ Tech Basket", "Nasdaq-100 relative strength", "QQQ", "stock", "momentum", "1h", "medium", "basic", True, 68.4, 998),
    ("iwm_small", "IWM Small Cap", "Russell 2000 swings", "IWM", "stock", "swing", "4h", "high", "medium", True, 59.2, 512),
    ("vix_hedge", "VIX Hedge Adjuster", "Raises cash when fear spikes", "VIX", "stock", "hedge", "1d", "high", "pro", True, 66.0, 187),
    ("eurusd_fx", "EURUSD Flow", "Major FX momentum", "EUR/USD", "crypto", "momentum", "1h", "medium", "medium", True, 64.1, 903),
    ("gbpjpy_fx", "GBPJPY Volatility", "Sterling-yen breakout system", "GBP/JPY", "crypto", "breakout", "4h", "high", "medium", True, 58.7, 412),
    ("bnb_momentum", "BNB Momentum", "BNB exchange-token trends", "BNB/USD", "crypto", "momentum", "1h", "medium", "basic", True, 61.5, 721),
    ("crv_defi", "CRV Curve", "DeFi pool momentum", "CRV/USD", "crypto", "swing", "4h", "high", "medium", True, 56.9, 355),
    ("pepe_momentum", "PEPE Momentum", "Meme volatility protocol", "PEPE/USD", "crypto", "momentum", "15m", "high", "basic", True, 52.3, 2104),
    ("corn_seasonal", "Corn Seasonal", "Planting/harvest drift", "ZC=F", "commodity", "seasonal", "1d", "medium", "basic", True, 67.8, 401),
    ("sugar_trend", "Sugar Trend", "Softs macro trend", "SB=F", "commodity", "momentum", "4h", "medium", "basic", True, 65.1, 288),
    ("brent_oil", "Brent Crude", "Brent vs WTI spread aware", "BZ=F", "commodity", "momentum", "1h", "high", "medium", True, 62.9, 512),
    ("jpm_bank", "JPM Financials", "Money-center bank trend", "JPM", "stock", "swing", "1d", "low", "basic", True, 72.4, 445),
    ("xle_energy", "XLE Energy Sector", "Integrated producers basket", "XLE", "stock", "swing", "4h", "medium", "basic", True, 63.6, 612),
]


def main() -> None:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    eng = create_engine(url, future=True)
    sql = text("""
    INSERT INTO trading_agents (
        id, name, description, symbol, category, strategy, timeframe, risk_level,
        min_tier, is_active, win_rate, total_trades
    ) VALUES (
        :id, :name, :description, :symbol, :category, :strategy, :timeframe, :risk_level,
        :min_tier, :is_active, :win_rate, :total_trades
    )
    ON CONFLICT (id) DO NOTHING
    """)
    with eng.begin() as c:
        for row in ROWS:
            keys = (
                "id",
                "name",
                "description",
                "symbol",
                "category",
                "strategy",
                "timeframe",
                "risk_level",
                "min_tier",
                "is_active",
                "win_rate",
                "total_trades",
            )
            payload = dict(zip(keys, row, strict=True))
            c.execute(sql, payload)
    print(f"Seeded up to {len(ROWS)} trading_agents (conflicts skipped).")


if __name__ == "__main__":
    main()
