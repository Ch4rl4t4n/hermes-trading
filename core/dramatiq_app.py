"""
Dramatiq broker bootstrap for Hermes Swarm v2.

Usage
-----
1. ``import core.dramatiq_app``  → broker is auto-configured.
2. Workers are launched via systemd (`hermes-workers@.service`) which calls
   ``dramatiq core.swarm_actors -p N -t M``.
3. Application code dispatches jobs via:

   .. code-block:: python

      from core.swarm_actors import route_task
      route_task.send(task_type="analyze_btc", payload={...})

The broker is **Redis-backed** with two queues:
  * ``hermes_default`` — generic workload (priority 5)
  * ``hermes_priority`` — urgent (priority 9-10)
  * ``hermes_low`` — bulk / analytics

Middleware stack:
  * Retries (max 3, exponential backoff)
  * AgeLimit (jobs older than 1h are dropped)
  * TimeLimit (default 5 min per actor)
  * CurrentMessage (so actors can introspect own message)
  * Prometheus (metrics endpoint at :9191)
"""
from __future__ import annotations

import logging
import os

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import (
    AgeLimit,
    Callbacks,
    CurrentMessage,
    Pipelines,
    Retries,
    ShutdownNotifications,
    TimeLimit,
)

log = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
NAMESPACE = os.getenv("HERMES_DRAMATIQ_NAMESPACE", "hermes")
ENABLE_PROMETHEUS = os.getenv("HERMES_ENABLE_PROMETHEUS", "0") == "1"


def _add_middleware_once(broker: RedisBroker, middleware_obj) -> None:
    """Avoid duplicate middleware warnings across forks/import paths."""
    middleware_type = type(middleware_obj)
    for existing in getattr(broker, "middleware", []):
        if isinstance(existing, middleware_type):
            return
    broker.add_middleware(middleware_obj)


def build_broker() -> RedisBroker:
    """Construct & install the global Dramatiq broker."""
    broker = RedisBroker(url=REDIS_URL, namespace=NAMESPACE)

    # Ensure deterministic middleware order (Dramatiq registers some by default).
    _add_middleware_once(broker, AgeLimit(max_age=60 * 60 * 1000))           # 1h
    _add_middleware_once(broker, TimeLimit(time_limit=5 * 60 * 1000))        # 5min
    _add_middleware_once(broker, Callbacks())
    _add_middleware_once(broker, Pipelines())
    _add_middleware_once(broker, Retries(max_retries=3, min_backoff=5_000, max_backoff=300_000))
    _add_middleware_once(broker, CurrentMessage())
    _add_middleware_once(broker, ShutdownNotifications())

    if ENABLE_PROMETHEUS:
        try:
            from dramatiq.middleware import Prometheus  # type: ignore
            _add_middleware_once(broker, Prometheus())
        except Exception:  # noqa: BLE001
            log.warning("prometheus middleware unavailable, skipping")

    dramatiq.set_broker(broker)
    log.info("[Dramatiq] broker ready at %s (ns=%s)", REDIS_URL, NAMESPACE)
    return broker


# Auto-configure on import unless caller opts out (e.g. unit tests).
if os.getenv("HERMES_SKIP_DRAMATIQ_AUTOSETUP", "0") != "1":
    broker = build_broker()
else:
    broker = None  # type: ignore[assignment]


# Queue name constants — import these instead of magic strings.
QUEUE_DEFAULT = "hermes_default"
QUEUE_PRIORITY = "hermes_priority"
QUEUE_LOW = "hermes_low"
