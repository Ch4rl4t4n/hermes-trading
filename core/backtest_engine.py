from __future__ import annotations

from datetime import date

import numpy as np


def generate_price_series(symbol: str, start_date: date, end_date: date, timeframe: str = "1d") -> list[float]:
    """
    Generate synthetic yet realistic prices with Geometric Brownian Motion.
    Intended as deterministic fallback until a real market data API is wired in.
    """
    base_prices = {
        "BTC/USD": 45000,
        "ETH/USD": 2500,
        "SOL/USD": 120,
        "NVDA": 800,
        "AAPL": 185,
        "MSFT": 420,
        "TSLA": 200,
        "XAU/USD": 2000,
        "OIL/USD": 80,
    }
    base = float(base_prices.get(symbol, 100.0))
    days = max(1, int((end_date - start_date).days))
    timeframe_norm = str(timeframe or "1d").lower()
    if timeframe_norm == "1h":
        n = max(24, days * 24)
        dt = 1 / 8760
    elif timeframe_norm == "4h":
        n = max(6, days * 6)
        dt = 1 / 2190
    else:
        n = max(2, days)
        dt = 1 / 365

    volatility = {
        "BTC/USD": 0.6,
        "ETH/USD": 0.7,
        "SOL/USD": 0.9,
        "NVDA": 0.5,
        "AAPL": 0.25,
        "MSFT": 0.25,
        "TSLA": 0.6,
        "XAU/USD": 0.15,
        "OIL/USD": 0.3,
    }.get(symbol, 0.3)
    drift = 0.15

    prices = [base]
    np.random.seed(42)
    for _ in range(n - 1):
        shock = np.random.normal(0, 1)
        price = prices[-1] * np.exp((drift - 0.5 * volatility**2) * dt + volatility * np.sqrt(dt) * shock)
        prices.append(max(float(price), base * 0.1))
    return prices


def run_backtest(
    symbol: str,
    strategy: str,
    start_date: date,
    end_date: date,
    initial_capital: float = 10000,
    timeframe: str = "1d",
    risk_level: str = "medium",
) -> dict:
    prices = generate_price_series(symbol, start_date, end_date, timeframe)
    strategy_norm = str(strategy or "momentum").strip().lower()
    if strategy_norm == "grid":
        # Grid maps closest to breakout behavior in this simplified simulator.
        strategy_norm = "breakout"

    capital = float(initial_capital)
    position = 0.0
    entry_price = 0.0
    trades = []
    equity_curve = [capital]
    risk_multiplier = {"low": 0.05, "medium": 0.1, "high": 0.2}.get(str(risk_level or "medium").lower(), 0.1)

    for i in range(20, len(prices)):
        price = float(prices[i])
        window = prices[i - 20 : i]
        ma20 = float(np.mean(window))
        ma5 = float(np.mean(prices[i - 5 : i]))
        signal = None

        if strategy_norm == "momentum":
            if ma5 > ma20 * 1.02 and position == 0:
                signal = "BUY"
            elif ma5 < ma20 * 0.98 and position > 0:
                signal = "SELL"
        elif strategy_norm == "mean_reversion":
            std = float(np.std(window))
            if price < ma20 - 1.5 * std and position == 0:
                signal = "BUY"
            elif price > ma20 + 1.0 * std and position > 0:
                signal = "SELL"
        elif strategy_norm == "dca":
            if i % 7 == 0:
                signal = "BUY"
            elif capital + position * price > initial_capital * 1.1 and position > 0:
                signal = "SELL"
        elif strategy_norm == "breakout":
            high20 = max(prices[i - 20 : i])
            low20 = min(prices[i - 20 : i])
            if price > high20 * 0.99 and position == 0:
                signal = "BUY"
            elif price < low20 * 1.01 and position > 0:
                signal = "SELL"

        if signal == "BUY" and capital > price * 10:
            invest = capital * risk_multiplier
            qty = invest / price
            position += qty
            capital -= invest
            entry_price = price
        elif signal == "SELL" and position > 0:
            proceeds = position * price
            basis = position * entry_price
            pnl = proceeds - basis
            trades.append(
                {
                    "i": i,
                    "side": "SELL",
                    "price": round(price, 2),
                    "pnl": round(pnl, 2),
                    "return_pct": round((pnl / basis) * 100, 2) if basis > 0 else 0.0,
                }
            )
            capital += proceeds
            position = 0.0
            entry_price = 0.0

        equity_curve.append(capital + position * price)

    final_capital = capital + position * prices[-1]
    total_return = ((final_capital - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0.0
    winning = [t for t in trades if float(t.get("pnl") or 0) > 0]
    win_rate = (len(winning) / len(trades) * 100) if trades else 0.0

    peak = float(initial_capital)
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    eq = np.array(equity_curve, dtype=float)
    if len(eq) > 1:
        returns = np.diff(eq) / np.where(eq[:-1] == 0, 1, eq[:-1])
    else:
        returns = np.array([], dtype=float)
    sharpe = float((np.mean(returns) / np.std(returns) * np.sqrt(252)) if len(returns) > 1 and np.std(returns) > 0 else 0.0)

    step = max(1, len(equity_curve) // 200)
    equity_normalized = equity_curve[::step][:200]

    return {
        "final_capital": round(float(final_capital), 2),
        "total_return": round(float(total_return), 2),
        "max_drawdown": round(float(max_dd * 100), 2),
        "win_rate": round(float(win_rate), 2),
        "total_trades": int(len(trades)),
        "winning_trades": int(len(winning)),
        "sharpe_ratio": round(float(sharpe), 3),
        "equity_curve": [round(float(v), 2) for v in equity_normalized],
        "trades_log": trades[-20:],
    }
