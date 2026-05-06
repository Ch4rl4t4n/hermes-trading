"""LLM layer unit tests — no real Anthropic calls."""
import sys
import types
from pathlib import Path
from datetime import time as dtime
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent, AgentConfig, SignalResult
from core.llm_advisor import (
    LLMAdvisor,
    get_llm_advisor,
    parse_llm_action_json,
    _model_for_request,
)
from tests.test_base_agent import make_config, ConcreteAgent


# ── JSON parsing ─────────────────────────────────────────────────────────────

def test_parse_json_plain() -> None:
    d = parse_llm_action_json('{"action": "BUY", "reason": "ok"}')
    assert d["action"] == "BUY"
    assert d["reason"] == "ok"


def test_parse_json_fenced() -> None:
    text = '```json\n{"action": "HOLD", "reason": "risk-off"}\n```'
    d = parse_llm_action_json(text)
    assert d["action"] == "HOLD"


def test_parse_json_extra_text() -> None:
    t = 'Here: {"action": "SELL", "reason": "x"} thanks'
    d = parse_llm_action_json(t)
    assert d["action"] == "SELL"


# ── Model routing ────────────────────────────────────────────────────────────

def test_model_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_LLM_HAIKU_MODEL", raising=False)
    monkeypatch.delenv("HERMES_LLM_SONNET_MODEL", raising=False)
    assert "haiku" in _model_for_request(False).lower()
    assert "sonnet" in _model_for_request(True).lower()


# ── Rate limit (BaseAgent method bound to test stub) ──────────────────────────

def test_llm_rate_limit_allows() -> None:
    a = ConcreteAgent(
        make_config(llm_max_calls_per_hour=3, llm_use_sonnet_above=0.9),
    )
    a._llm_rate_limit_allows = types.MethodType(  # type: ignore[assignment]
        BaseAgent._llm_rate_limit_allows, a
    )
    a.llm_calls_this_hour = 0
    a._llm_hour = -1
    assert a._llm_rate_limit_allows() is True
    a.llm_calls_this_hour = 2
    assert a._llm_rate_limit_allows() is True
    a.llm_calls_this_hour = 3
    assert a._llm_rate_limit_allows() is False


# ── Async review (mocked API) ────────────────────────────────────────────────

class _MinAgent:
    name = "Unit"
    symbol = "TEST"
    position_qty = 0.0
    entry_price = None
    prices = [100.0] * 25

    def __init__(self) -> None:
        self.cfg = make_config(
            llm_use_sonnet_above=0.9,
        )

    def get_llm_context(self) -> str:
        return "test context"

    def calculate_rsi(self) -> float:
        return 45.0

    def calculate_vwap(self) -> float:
        return 99.5


@pytest.mark.asyncio
async def test_review_signal_parses_buy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import core.llm_advisor as llm_mod

    llm_mod._advisor = None
    adv = LLMAdvisor()
    assert adv.is_configured()

    mock_text = MagicMock()
    mock_text.text = '{"action": "BUY", "reason": "aligned with macro"}'
    mock_resp = MagicMock()
    mock_resp.content = [mock_text]
    mock_u = MagicMock()
    mock_u.input_tokens = 100
    mock_u.output_tokens = 30
    mock_resp.usage = mock_u

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=mock_resp)
    adv._client = client  # type: ignore[assignment]

    agent = _MinAgent()
    sig = SignalResult(direction="BUY", confidence=0.72, reason="RSI test")
    out, meta = await adv.review_signal(agent, sig)  # type: ignore[arg-type]

    assert out.direction == "BUY"
    assert "[LLM OK" in out.reason
    assert meta.get("model")
    assert client.messages.create.called


@pytest.mark.asyncio
async def test_get_llm_advisor_singleton() -> None:
    import core.llm_advisor as llm_mod

    llm_mod._advisor = None
    a1 = get_llm_advisor()
    a2 = get_llm_advisor()
    assert a1 is a2
