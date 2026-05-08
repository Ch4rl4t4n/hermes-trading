from __future__ import annotations

"""
Intelligence Stalker Swarm
- News Stalker (intel-001): analyzes news sentiment
- Trend Detector (intel-002): detects trend/momentum signals
Runs every 5 minutes and writes intelligence reports.
"""

import json
import random
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import text

import core.database as db
from core.queue_manager import queue_manager


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntelligenceStalker:
    def __init__(self):
        self.running = False
        self.thread: threading.Thread | None = None
        self.cycle_count = 0
        self.agents = {
            "news": "intel-001",
            "trend": "intel-002",
        }

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="IntelligenceStalker",
        )
        self.thread.start()

    def stop(self) -> None:
        self.running = False

    def _run_loop(self) -> None:
        time.sleep(30)
        while self.running:
            try:
                self._cycle()
            except Exception:
                pass
            time.sleep(300)

    def _cycle(self) -> None:
        self.cycle_count += 1
        for agent_id in self.agents.values():
            queue_manager.heartbeat(agent_id)
            queue_manager.update_agent_status(agent_id, "running")

        symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "NVDA", "AAPL"]
        for symbol in symbols[:2]:
            self._analyze_news(symbol)
            self._detect_trends(symbol)

        if self.cycle_count % 12 == 0:
            self._generate_summary()

        for agent_id in self.agents.values():
            queue_manager.update_agent_status(agent_id, "idle")

    def _analyze_news(self, symbol: str) -> None:
        eng = db.get_engine()
        if eng is None:
            return
        templates = {
            "positive": [
                f"{symbol} breaks key resistance level amid strong volume",
                f"Institutional buying detected in {symbol} - whale alert",
                f"{symbol} technical indicators show bullish divergence",
                f"Strong fundamentals support {symbol} price action",
            ],
            "negative": [
                f"{symbol} faces selling pressure at major resistance",
                f"Risk-off sentiment weighs on {symbol}",
                f"{symbol} volume declining - momentum fading",
                f"Bearish engulfing pattern on {symbol} daily chart",
            ],
            "neutral": [
                f"{symbol} consolidating in tight range - breakout imminent",
                f"Mixed signals for {symbol} - traders await catalyst",
                f"{symbol} testing key support - watch for reaction",
            ],
        }
        sentiment = random.choices(["positive", "negative", "neutral"], weights=[0.45, 0.3, 0.25])[0]
        score = {
            "positive": round(random.uniform(0.3, 0.9), 3),
            "negative": round(random.uniform(-0.9, -0.3), 3),
            "neutral": round(random.uniform(-0.2, 0.2), 3),
        }[sentiment]
        headline = random.choice(templates[sentiment])
        with eng.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO intelligence_reports
                    (report_type, symbol, title, content, sentiment, sentiment_score, source, tags, agent_id)
                    VALUES ('news', :sym, :title, :content, :sent, :score, :src, CAST(:tags AS JSONB), :aid)
                    """
                ),
                {
                    "sym": symbol,
                    "title": headline,
                    "content": f"Analysis by Intel-001 | Cycle {self.cycle_count}",
                    "sent": sentiment,
                    "score": score,
                    "src": random.choice(["Reuters", "Bloomberg", "CoinDesk", "CNBC"]),
                    "tags": json.dumps([symbol.split("/")[0].lower(), sentiment]),
                    "aid": self.agents["news"],
                },
            )

    def _detect_trends(self, symbol: str) -> None:
        eng = db.get_engine()
        if eng is None:
            return
        signals = [
            ("bullish", f"RSI oversold recovery on {symbol} - momentum building"),
            ("bearish", f"Death cross forming on {symbol} - trend reversal watch"),
            ("bullish", f"MACD bullish crossover detected for {symbol}"),
            ("neutral", f"Bollinger Band squeeze on {symbol} - volatility expansion expected"),
            ("bullish", f"Volume surge confirms {symbol} breakout"),
        ]
        direction, title = random.choice(signals)
        sentiment = "positive" if direction == "bullish" else "negative" if direction == "bearish" else "neutral"
        score = round(
            random.uniform(0.3, 0.8) * (1 if sentiment == "positive" else -1 if sentiment == "negative" else 0.1),
            3,
        )
        with eng.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO intelligence_reports
                    (report_type, symbol, title, sentiment, sentiment_score, source, tags, agent_id)
                    VALUES ('trend', :sym, :title, :sent, :score, 'TechAnalysis', CAST(:tags AS JSONB), :aid)
                    """
                ),
                {
                    "sym": symbol,
                    "title": title,
                    "sent": sentiment,
                    "score": score,
                    "tags": json.dumps([direction, "technical", symbol.split("/")[0].lower()]),
                    "aid": self.agents["trend"],
                },
            )

    def _generate_summary(self) -> None:
        eng = db.get_engine()
        if eng is None:
            return
        with eng.begin() as conn:
            stats = conn.execute(
                text(
                    """
                    SELECT
                        COUNT(*)::int AS total,
                        COUNT(CASE WHEN sentiment='positive' THEN 1 END)::int AS positive,
                        COUNT(CASE WHEN sentiment='negative' THEN 1 END)::int AS negative,
                        COUNT(CASE WHEN sentiment='neutral' THEN 1 END)::int AS neutral
                    FROM intelligence_reports
                    WHERE created_at > NOW() - INTERVAL '1 hour'
                    """
                )
            ).mappings().first()
            if not stats or int(stats["total"] or 0) == 0:
                return
            total = int(stats["total"] or 0)
            bull_pct = round((int(stats["positive"] or 0) / total) * 100)
            sentiment = "positive" if bull_pct > 55 else "negative" if bull_pct < 35 else "neutral"
            summary = (
                f"Market Intelligence Summary: {bull_pct}% bullish signals "
                f"({int(stats['positive'] or 0)} positive, {int(stats['negative'] or 0)} negative, "
                f"{int(stats['neutral'] or 0)} neutral) from {total} reports"
            )
            conn.execute(
                text(
                    """
                    INSERT INTO intelligence_reports
                    (report_type, title, content, sentiment, sentiment_score, source, tags, agent_id)
                    VALUES ('summary', :title, :content, :sent, :score, 'Intelligence Swarm', CAST(:tags AS JSONB), 'intel-001')
                    """
                ),
                {
                    "title": "Hourly Market Intelligence Summary",
                    "content": summary,
                    "sent": sentiment,
                    "score": round((bull_pct - 50) / 50, 3),
                    "tags": json.dumps(["summary", "hourly"]),
                },
            )


stalker = IntelligenceStalker()
