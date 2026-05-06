"""Synthetic, human-readable trade rationales for marketplace paper trades."""

from __future__ import annotations

import random
from typing import Any


def _rand_rsi(zone: str) -> int:
    return random.randint(22, 32) if zone == "oversold" else random.randint(68, 78)


def _rand_pct(lo: int, hi: int) -> int:
    return random.randint(lo, hi)


def _rand_float(lo: float, hi: float) -> float:
    return random.uniform(lo, hi)


def _rand_int(lo: int, hi: int) -> int:
    return random.randint(lo, hi)


def _normalize_strategy(raw: str | None) -> str:
    s = (raw or "momentum").strip().lower().replace(" ", "_")
    aliases = {
        "scalp": "scalping",
        "hedge": "momentum",
        "seasonal": "swing",
        "value": "dca",
        "growth": "momentum",
    }
    return aliases.get(s, s)


def generate_trade_reason(
    agent: dict[str, Any],
    action: str,  # 'buy' or 'sell'
    symbol: str,
    price: float,
    pnl: float = 0.0,
) -> dict[str, Any]:
    """Return ``{ reason, signals, confidence }`` for a paper trade row."""
    strategy = _normalize_strategy(agent.get("strategy") if isinstance(agent, dict) else None)
    category = str((agent.get("category") if isinstance(agent, dict) else None) or "crypto").lower()

    strategy_signals: dict[str, dict[str, list[str]]] = {
        "momentum": {
            "buy": [
                f"RSI ({_rand_rsi('oversold')}) — oversold zóna",
                "MACD crossover bullish potvrdzuje trend",
                f"Volume spike +{_rand_pct(20, 80)}% nad 20-dňovým priemerom",
            ],
            "sell": [
                f"RSI ({_rand_rsi('overbought')}) — overbought zóna",
                "MACD divergencia — momentum slabne",
                f"Take profit dosiahnutý (+{abs(pnl):.1f} USD)",
            ],
        },
        "dca": {
            "buy": [
                "Pravidelný DCA nákup podľa plánu",
                f"Cena {_rand_pct(2, 8)}% pod 30-dňovým priemerom",
                "Optimálne načasovanie v rámci DCA okna",
            ],
            "sell": [
                "DCA cieľová cena dosiahnutá",
                f"Profit target +{abs(pnl):.1f} USD splnený",
                "Rebalancing portfólia",
            ],
        },
        "swing": {
            "buy": [
                "Support level potvrdený (3. dotyk)",
                f"Bullish engulfing sviečka na {symbol}",
                "Vyšší objem potvrdzuje breakout",
            ],
            "sell": [
                "Resistance level dosiahnutý",
                "Bearish reversal pattern detekovaný",
                "Stop-loss alebo profit target aktivovaný",
            ],
        },
        "breakout": {
            "buy": [
                f"Breakout nad kľúčový odpor pri {price:.2f}",
                f"Volume {_rand_pct(50, 150)}% nad normálom",
                "Potvrdzujúca sviečka uzavrela nad úrovňou",
            ],
            "sell": [
                "Breakout zlyhával — návrat pod odpor",
                f"Stop-loss aktivovaný pri {price:.2f}",
                "Risk management pravidlo dodržané",
            ],
        },
        "mean_reversion": {
            "buy": [
                f"Zóna prepredanosti — očakávaný návrat k priemeru pri {price:.2f}",
                "Bollinger band spodný pás + RSI divergence",
                "Arbitrage flow naznačuje short-covering",
            ],
            "sell": [
                "Cena nad historickým priemerom — fixácia zisku",
                f"RSI stretched — profit taking pri {price:.2f}",
                "Mean-reversion target splnený",
            ],
        },
        "trend_following": {
            "buy": [
                "HTF trend intact — pullback kúpna zóna",
                f"ADX potvrdzuje silný trend pri {price:.2f}",
                "Higher lows séria pokračuje",
            ],
            "sell": [
                "Break trendline na nižšom timeframe",
                "Trailing stop aktivovaný podľa ATR",
                f"Trend exhaustion signály pri {price:.2f}",
            ],
        },
        "scalping": {
            "buy": [
                f"Quick bounce z intraday support {price:.2f}",
                "Order flow imbalance bullish < 5m",
                "Micro structure higher high",
            ],
            "sell": [
                "Scalp target +0.15–0.35 % dosiahnutý",
                f"Tight stop hit — liquidity sweep pri {price:.2f}",
                "Spread compression — exit",
            ],
        },
        "grid": {
            "buy": [
                f"Grid level fill — dolný pás {price:.2f}",
                "Automatický rebuy podľa mriežky",
                "DCA grid trigger",
            ],
            "sell": [
                f"Horný grid level — partial sell pri {price:.2f}",
                "Grid rebalance dokončený",
                "Profit band z uzavretého páru",
            ],
        },
        "sentiment": {
            "buy": [
                f"News sentiment score: {_rand_float(0.6, 0.9):.2f} (pozitívny)",
                f"Fear & Greed index: {_rand_int(15, 35)} (Extreme Fear = buy signal)",
                "Social media buzz +47% za posledné 4h",
            ],
            "sell": [
                f"Sentiment otočil na negatívny ({_rand_float(0.2, 0.45):.2f})",
                "Fear & Greed: Extreme Greed — čas predávať",
                "Unusual whale activity detekovaná",
            ],
        },
    }

    act = (action or "buy").strip().lower()
    if act not in ("buy", "sell"):
        act = "buy"

    bucket = strategy_signals.get(strategy, strategy_signals["momentum"])
    signals_list = bucket.get(act, bucket.get("buy", strategy_signals["momentum"]["buy"]))

    k = min(len(signals_list), max(1, random.randint(2, 3)))
    selected = random.sample(signals_list, k)

    sentiment_ctx = {
        "crypto": f"Crypto market regime: {'bullish' if act == 'buy' else 'bearish'}",
        "stock": f"Market regime: {'risk-on' if act == 'buy' else 'risk-off'}",
        "commodity": f"Commodity trend: {'uptrend' if act == 'buy' else 'correction'}",
    }.get(category, "")

    action_word = "Kúpa" if act == "buy" else "Predaj"
    second = selected[1] if len(selected) > 1 else ""
    reason = f"{action_word} {symbol} @ {price:.4f} — {selected[0]}."
    if second:
        reason += f" {second}."

    signals: dict[str, Any] = {
        "technical": selected,
        "sentiment": [sentiment_ctx] if sentiment_ctx else [],
        "regime": "trending_up" if act == "buy" else "trending_down",
        "risk": random.choice(["low", "medium"]) if act == "buy" else "managed",
    }

    confidence = round(random.uniform(0.62, 0.91), 2)

    return {
        "reason": reason,
        "signals": signals,
        "confidence": confidence,
    }
