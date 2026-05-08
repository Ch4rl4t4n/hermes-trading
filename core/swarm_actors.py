"""
Dramatiq actors for Hermes Swarm v2.

Each actor is a unit of work that workers can execute. The Task Router
dispatches `route_task.send(...)` and the Orchestra periodic actor
(`orchestra_tick`) keeps the swarm healthy.

Actors split by queue:
  * priority queue → urgent trade execution / alerts
  * default queue  → routing + generic workload
  * low queue      → analytics, snapshots, cleanup

Run with:
    dramatiq core.swarm_actors -p 4 -t 8 -q hermes_default hermes_priority
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import dramatiq
from sqlalchemy import text

try:
    from core.dramatiq_app import QUEUE_DEFAULT, QUEUE_LOW, QUEUE_PRIORITY  # noqa: F401  re-export
    from core.swarm_registry import get_engine, swarm_registry
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from hermes.core.dramatiq_app import QUEUE_DEFAULT, QUEUE_LOW, QUEUE_PRIORITY  # noqa: F401  re-export
    from hermes.core.swarm_registry import get_engine, swarm_registry

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Task lifecycle helpers ────────────────────────────────────────────────
def _persist_task_status(
    task_id: str,
    status: str,
    *,
    assigned_to: str | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    execution_time_ms: int | None = None,
) -> None:
    eng = get_engine()
    if eng is None:
        return
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE task_queue SET
                    status = :status,
                    assigned_to = COALESCE(:assigned, assigned_to),
                    result = CAST(:result AS JSONB),
                    error_message = :err,
                    execution_time_ms = COALESCE(:ms, execution_time_ms),
                    started_at = CASE WHEN :status = 'running' THEN COALESCE(started_at, NOW()) ELSE started_at END,
                    completed_at = CASE WHEN :status IN ('completed','failed','dead') THEN NOW() ELSE completed_at END
                WHERE task_id = :tid
                """
            ),
            {
                "tid": task_id,
                "status": status,
                "assigned": assigned_to,
                "result": json.dumps(result) if result is not None else None,
                "err": error,
                "ms": execution_time_ms,
            },
        )


# ── Generic dispatcher ────────────────────────────────────────────────────
@dramatiq.actor(queue_name=QUEUE_DEFAULT, max_retries=3, time_limit=300_000)
def execute_task(task_id: str, agent_id: str, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Generic task executor.

    Concrete handlers register themselves in TASK_HANDLERS below.
    Unknown task types are persisted as completed with a "noop" reason
    (so we never lose audit). For trading / intel tasks, register
    domain-specific actors and delegate via `dramatiq.Message.dispatch`.
    """
    started = time.monotonic()
    swarm_registry.update_load(agent_id, +1)
    swarm_registry.mark_status(agent_id, "running")
    _persist_task_status(task_id, "running", assigned_to=agent_id)
    try:
        handler = TASK_HANDLERS.get(task_type)
        if handler is None:
            log.info("[execute_task] no handler for %s — marking noop", task_type)
            result = {"noop": True, "task_type": task_type}
        else:
            result = handler(payload) or {}
        ms = int((time.monotonic() - started) * 1000)
        _persist_task_status(task_id, "completed", assigned_to=agent_id, result=result, execution_time_ms=ms)
        return result
    except Exception as exc:  # noqa: BLE001
        ms = int((time.monotonic() - started) * 1000)
        _persist_task_status(task_id, "failed", assigned_to=agent_id, error=str(exc), execution_time_ms=ms)
        log.exception("[execute_task] task %s failed", task_id)
        raise
    finally:
        swarm_registry.update_load(agent_id, -1)
        current = swarm_registry.get_agent(agent_id) or {}
        active_now = int(current.get("active_tasks") or 0)
        swarm_registry.mark_status(agent_id, "idle" if active_now <= 0 else "running")
        swarm_registry.heartbeat(agent_id)


# ── Routing actor: receives intent, finds best agent, schedules execute ──
@dramatiq.actor(queue_name=QUEUE_DEFAULT, max_retries=2, time_limit=30_000)
def route_task(
    task_type: str,
    payload: dict[str, Any] | None = None,
    priority: int = 5,
    required_capabilities: list[str] | None = None,
    preferred_swarm: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    try:
        from core.task_router import task_router  # local import → avoid circular
    except ModuleNotFoundError:
        from hermes.core.task_router import task_router
    decision = task_router.route_task(
        task_type=task_type,
        payload=payload or {},
        priority=int(priority),
        required_capabilities=required_capabilities,
        preferred_swarm=preferred_swarm,
        task_id=task_id,
    )
    if decision.get("assigned_agent") and decision.get("task_id"):
        target_queue = QUEUE_PRIORITY if int(priority) >= 8 else QUEUE_DEFAULT
        execute_task.send_with_options(
            args=(decision["task_id"], decision["assigned_agent"], task_type, payload or {}),
            queue_name=target_queue,
        )
    return decision


# ── Orchestra heartbeat / housekeeping ────────────────────────────────────
@dramatiq.actor(queue_name=QUEUE_LOW, max_retries=0, time_limit=30_000)
def orchestra_tick() -> None:
    """Runs every 30s (scheduled externally by orchestra_agent.py)."""
    swarm_registry.heartbeat("orchestra-001")
    reaped = swarm_registry.reap_dead()
    cleaned = swarm_registry.cleanup_stopped()
    eng = get_engine()
    pending = 0
    if eng is not None:
        with eng.connect() as conn:
            pending = int(conn.execute(
                text("SELECT COUNT(*)::int FROM task_queue WHERE status = 'pending'")
            ).scalar() or 0)
    log.info("[orchestra_tick] pending=%s reaped=%s cleaned=%s at=%s", pending, reaped, cleaned, _now_iso())
    return None


# ── Task handler registry ─────────────────────────────────────────────────
# Domain-specific business logic is plugged in here. Each handler is a
# pure function `(payload: dict) -> dict`. Long-running work belongs in
# its own actor; this is for short, in-process logic.
TASK_HANDLERS: dict[str, Any] = {
    "ping": lambda p: {"pong": True, "echo": p},
    "noop": lambda p: {"ok": True},
}


def register_handler(task_type: str, handler) -> None:
    """Register a handler function from another module (idempotent)."""
    TASK_HANDLERS[task_type] = handler
    log.info("[Swarm] handler registered for task_type=%s", task_type)


# Auto-register domain handlers so Dramatiq workers (which only import this
# module) have full coverage. Disable via HERMES_SKIP_HANDLER_AUTOLOAD=1.
import os as _os  # noqa: E402

if _os.getenv("HERMES_SKIP_HANDLER_AUTOLOAD", "0") != "1":
    try:
        try:
            from core.swarm_handlers import register_all as _register_all_handlers
        except ModuleNotFoundError:
            from hermes.core.swarm_handlers import register_all as _register_all_handlers
        _register_all_handlers()
    except Exception:  # noqa: BLE001
        log.warning("[Swarm] domain handler autoload failed", exc_info=True)
