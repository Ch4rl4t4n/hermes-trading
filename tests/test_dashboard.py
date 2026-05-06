"""Dashboard API (FastAPI) smoke tests."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ["DASHBOARD_API_KEY"] = "test-secret-key-hex"


class _H:
    """Minimal hermes stand-in for the dashboard app."""

    def __init__(self) -> None:
        import asyncio

        from agents.base_agent import AgentConfig
        from datetime import time as dtime

        self.kill_event = asyncio.Event()
        self.agents: list = []
        self.feed = _Feed()

        # one fake agent
        cfg = AgentConfig(
            name="X", symbol="BTC/USD", asset_type="crypto", enabled=True, trade_usd=10.0,
            timezone="UTC", active_hours_start=dtime(0, 0), active_hours_end=dtime(23, 59),
            check_interval_seconds=60, rsi_period=14, rsi_buy_threshold=30.0, rsi_sell_threshold=70.0,
            macd_enabled=True, signal_confidence_threshold=0.5, llm_enabled=False,
            llm_trigger_threshold=0.5, llm_model="h", llm_max_calls_per_hour=6, llm_use_sonnet_above=0.9,
            trailing_stop_pct=3.0, take_profit_pct=8.0, max_trades_per_day=5, max_daily_loss_pct=2.0,
            max_position_pct=0.05, timeframe="1h", trailing_activate_pct=0.0, atr_position_sizing=False,
        )
        a = _A(cfg)
        a.prices = [100.0] * 30
        a.position_qty = 0.0
        self.agents.append(a)


class _Feed:
    def get_price(self, sym: str) -> float:
        return 100.0


class _A:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.name = "Test"
        self.symbol = cfg.symbol
        self.prices = [100.0] * 30
        self.position_qty = 0.0
        self.trades_today = 0
        self.entry_price = None
        self.paused_manually = False
        self.paused_by_limit = False

    def _get_portfolio_value(self) -> float:
        return 50_000.0


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from core.dashboard_app import create_dashboard_app

    h = _H()
    return TestClient(create_dashboard_app(h))


def test_status_requires_key(client) -> None:
    r = client.get("/api/status")
    assert r.status_code == 401


def test_status_ok_with_header(client) -> None:
    r = client.get("/api/status", headers={"X-API-Key": "test-secret-key-hex"})
    assert r.status_code == 200
    data = r.json()
    assert "kill_switch" in data
    assert data["agents"] == 1


def test_index_public(client) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert b"LETAGENTSCOOK" in r.content


def test_kill_requires_key(client) -> None:
    r = client.post("/api/kill")
    assert r.status_code == 401


def test_login_default_shako(client) -> None:
    r = client.post("/api/auth/login", json={"username": "shako", "password": "shako"})
    assert r.status_code == 200
    assert r.json().get("ok") is True
    s = client.get("/api/status")
    assert s.status_code == 200
    assert s.json()["agents"] == 1


def test_login_rejects_wrong_password(client) -> None:
    r = client.post("/api/auth/login", json={"username": "shako", "password": "wrong"})
    assert r.status_code == 401


def test_logout_clears_session(client) -> None:
    client.post("/api/auth/login", json={"username": "shako", "password": "shako"})
    assert client.get("/api/status").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/status").status_code == 401
