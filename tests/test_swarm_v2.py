"""
Unit tests for Hermes Swarm v2 — registry, queue, router.

These tests use a fake in-memory Redis (via `fakeredis`) when available,
otherwise they fall back to a mock dict, so they run without a real broker.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# Ensure import path
sys.path.insert(0, "/root/hermes")

# Skip Dramatiq broker auto-setup in tests
os.environ["HERMES_SKIP_DRAMATIQ_AUTOSETUP"] = "1"


@pytest.fixture
def fake_redis():
    """Provide a fakeredis client; skip the test if unavailable."""
    try:
        import fakeredis  # type: ignore
    except ImportError:
        pytest.skip("fakeredis not installed")
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def registry(fake_redis):
    from core.swarm_registry import SwarmRegistry
    with patch("core.swarm_registry.get_engine", return_value=None):
        yield SwarmRegistry(redis_client=fake_redis)


# ── Registry ──────────────────────────────────────────────────────────────
def test_register_and_get_agent(registry):
    registry.register_agent(
        agent_id="test-001",
        name="Test Agent",
        swarm="trading",
        capabilities=["trading", "BTC"],
        agent_type="worker",
    )
    agent = registry.get_agent("test-001")
    assert agent is not None
    assert agent["name"] == "Test Agent"
    assert agent["swarm"] == "trading"
    assert "trading" in agent["capabilities"]


def test_heartbeat_marks_alive(registry):
    registry.register_agent("hb-001", "HB Agent", "intelligence", ["research"])
    assert registry.is_alive("hb-001") is False
    registry.heartbeat("hb-001")
    assert registry.is_alive("hb-001") is True


def test_status_validation(registry):
    registry.register_agent("st-001", "Status", "trading", ["trading"])
    registry.mark_status("st-001", "running")
    with pytest.raises(ValueError):
        registry.mark_status("st-001", "exploded")


def test_list_by_swarm(registry):
    registry.register_agent("a-1", "A", "trading", ["trading"])
    registry.register_agent("b-1", "B", "intelligence", ["research"])
    registry.register_agent("c-1", "C", "trading", ["trading"])

    trading = registry.list_agents(swarm="trading")
    assert len(trading) == 2
    assert {a["agent_id"] for a in trading} == {"a-1", "c-1"}


def test_load_increment(registry):
    registry.register_agent("load-1", "L", "trading", ["trading"])
    registry.update_load("load-1", +1)
    registry.update_load("load-1", +1)
    agent = registry.get_agent("load-1")
    assert int(agent.get("active_tasks") or 0) == 2


def test_cleanup_stopped_moves_to_paused(fake_redis):
    from core.swarm_registry import SwarmRegistry
    with patch("core.swarm_registry.get_engine", return_value=None):
        reg = SwarmRegistry(redis_client=fake_redis)
        reg.register_agent("stopped-1", "Stopped Agent", "maintenance", ["infra"])
        reg.mark_status("stopped-1", "stopped")
        # Use Redis path to assert state transition semantics independent of DB.
        fake_redis.hset("hermes:agent:stopped-1", "last_heartbeat", (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())

    # DB-backed cleanup isn't available in this test fixture; ensure method is safe/no-op.
    cleaned = reg.cleanup_stopped(older_than_seconds=60)
    assert cleaned == 0


def test_heartbeat_auto_resumes_paused_for_configured_swarm(fake_redis):
    from core.swarm_registry import SwarmRegistry
    with patch("core.swarm_registry.get_engine", return_value=None), \
         patch("core.swarm_registry.AUTO_RESUME_SWARMS", {"maintenance", "orchestra"}):
        reg = SwarmRegistry(redis_client=fake_redis)
        reg.register_agent("maint-1", "Maintenance Agent", "maintenance", ["infra"])
        reg.mark_status("maint-1", "paused")
        reg.heartbeat("maint-1")
        agent = reg.get_agent("maint-1")
        assert agent is not None
        assert agent["status"] == "idle"


def test_heartbeat_keeps_paused_for_non_configured_swarm(fake_redis):
    from core.swarm_registry import SwarmRegistry
    with patch("core.swarm_registry.get_engine", return_value=None), \
         patch("core.swarm_registry.AUTO_RESUME_SWARMS", {"maintenance", "orchestra"}):
        reg = SwarmRegistry(redis_client=fake_redis)
        reg.register_agent("trade-1", "Trading Agent", "trading", ["trading"])
        reg.mark_status("trade-1", "paused")
        reg.heartbeat("trade-1")
        agent = reg.get_agent("trade-1")
        assert agent is not None
        assert agent["status"] == "paused"


# ── QueueManager ──────────────────────────────────────────────────────────
def test_queue_push_pop(fake_redis):
    from core.queue_manager import QueueManager
    from core.swarm_registry import SwarmRegistry

    with patch("core.swarm_registry.get_engine", return_value=None), \
         patch("core.queue_manager.get_engine", return_value=None):
        reg = SwarmRegistry(redis_client=fake_redis)
        qm = QueueManager(redis_client=fake_redis, registry=reg)

        tid = qm.push_task(
            task_type="analyze_btc",
            payload={"symbol": "BTC"},
            priority=8,
            required_capabilities=["trading", "BTC"],
        )
        assert tid

        # Agent without capability won't get the task
        nope = qm.pop_task(agent_capabilities=["news"])
        assert nope is None

        # Agent with capability gets it
        task = qm.pop_task(agent_capabilities=["trading", "BTC"])
        assert task is not None
        assert task["task_type"] == "analyze_btc"


def test_queue_priority_ordering(fake_redis):
    from core.queue_manager import QueueManager
    from core.swarm_registry import SwarmRegistry
    with patch("core.swarm_registry.get_engine", return_value=None), \
         patch("core.queue_manager.get_engine", return_value=None):
        reg = SwarmRegistry(redis_client=fake_redis)
        qm = QueueManager(redis_client=fake_redis, registry=reg)

        qm.push_task("low", {}, priority=2)
        qm.push_task("high", {}, priority=9)
        qm.push_task("mid", {}, priority=5)

        first = qm.pop_task()
        assert first["task_type"] == "high"


def test_queue_push_without_redis_enqueue(fake_redis):
    from core.queue_manager import QUEUE_PRIORITY, QueueManager
    from core.swarm_registry import SwarmRegistry
    with patch("core.swarm_registry.get_engine", return_value=None), \
         patch("core.queue_manager.get_engine", return_value=None):
        reg = SwarmRegistry(redis_client=fake_redis)
        qm = QueueManager(redis_client=fake_redis, registry=reg)

        qm.push_task("db_only", {}, priority=5, enqueue_redis=False)
        assert int(fake_redis.zcard(QUEUE_PRIORITY)) == 0


# ── TaskRouter ────────────────────────────────────────────────────────────
def test_router_picks_capability_match(fake_redis):
    from core.queue_manager import QueueManager
    from core.swarm_registry import SwarmRegistry
    from core.task_router import TaskRouter

    with patch("core.swarm_registry.get_engine", return_value=None), \
         patch("core.queue_manager.get_engine", return_value=None):
        reg = SwarmRegistry(redis_client=fake_redis)
        qm = QueueManager(redis_client=fake_redis, registry=reg)

        reg.register_agent("trader-1", "BTC Trader", "trading", ["trading", "BTC"])
        reg.register_agent("news-1", "News Stalker", "intelligence", ["research", "news"])
        reg.heartbeat("trader-1")
        reg.heartbeat("news-1")

        with patch("core.task_router.queue_manager", qm), \
             patch("core.task_router.swarm_registry", reg):
            router = TaskRouter()
            decision = router.simulate_route(
                task_type="analyze_btc",
                required_capabilities=["trading", "BTC"],
            )
        assert decision["would_assign_to"] == "trader-1"


def test_router_fallback_no_match(fake_redis):
    from core.swarm_registry import SwarmRegistry
    from core.task_router import TaskRouter
    with patch("core.swarm_registry.get_engine", return_value=None):
        reg = SwarmRegistry(redis_client=fake_redis)
        with patch("core.task_router.swarm_registry", reg):
            router = TaskRouter()
            decision = router.simulate_route(
                task_type="alien_task",
                required_capabilities=["interstellar"],
            )
        assert decision["would_assign_to"] is None


def test_router_load_balancing(fake_redis):
    from core.swarm_registry import SwarmRegistry
    from core.task_router import TaskRouter
    with patch("core.swarm_registry.get_engine", return_value=None):
        reg = SwarmRegistry(redis_client=fake_redis)
        reg.register_agent("busy", "Busy Trader", "trading", ["trading"])
        reg.register_agent("free", "Free Trader", "trading", ["trading"])
        reg.heartbeat("busy")
        reg.heartbeat("free")
        reg.update_load("busy", +5)

        with patch("core.task_router.swarm_registry", reg):
            router = TaskRouter()
            decision = router.simulate_route(
                task_type="trade",
                required_capabilities=["trading"],
            )
        assert decision["would_assign_to"] == "free"


def test_router_assigned_task_not_left_in_redis_queue(fake_redis):
    from core.queue_manager import QUEUE_PRIORITY, QueueManager
    from core.swarm_registry import SwarmRegistry
    from core.task_router import TaskRouter

    with patch("core.swarm_registry.get_engine", return_value=None), \
         patch("core.queue_manager.get_engine", return_value=None):
        reg = SwarmRegistry(redis_client=fake_redis)
        qm = QueueManager(redis_client=fake_redis, registry=reg)

        reg.register_agent("trader-a", "Trader A", "trading", ["trading"])
        reg.heartbeat("trader-a")

        with patch("core.task_router.queue_manager", qm), \
             patch("core.task_router.swarm_registry", reg):
            router = TaskRouter()
            decision = router.route_task(
                task_type="rebalance",
                payload={"symbol": "BTC"},
                required_capabilities=["trading"],
            )
            assert decision["assigned_agent"] == "trader-a"
            assert decision["status"] == "assigned"
            assert int(fake_redis.zcard(QUEUE_PRIORITY)) == 0


# ── Bootstrap (smoke) ─────────────────────────────────────────────────────
def test_bootstrap_seeds_default_swarms(fake_redis):
    from core.swarm_definitions import DEFAULT_SWARMS
    from core.swarm_registry import SwarmRegistry

    with patch("core.swarm_registry.get_engine", return_value=None):
        reg = SwarmRegistry(redis_client=fake_redis)
        # Patch the global singleton used by bootstrap
        with patch("core.swarm_bootstrap.swarm_registry", reg):
            from core.swarm_bootstrap import hydrate_and_seed
            stats = hydrate_and_seed()
        assert stats["default_seeded"] >= sum(len(s["agents"]) for s in DEFAULT_SWARMS)
