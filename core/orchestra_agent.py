"""
Orchestra Agent — backwards-compatible shim.

Real periodic work happens via the Dramatiq actor `orchestra_tick` in
`core/swarm_actors.py`, scheduled by `core.swarm_bootstrap.orchestra_scheduler`.

This module exposes a minimal in-process façade `orchestra` so existing
callers (e.g. `dashboard/app.py` which calls `orchestra.start()`) keep
working without code changes.
"""
from __future__ import annotations

import logging

try:
    from core.swarm_bootstrap import bootstrap_swarm, orchestra_scheduler
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from hermes.core.swarm_bootstrap import bootstrap_swarm, orchestra_scheduler

log = logging.getLogger(__name__)


class OrchestraAgentFacade:
    """Compatibility shim exposing `start()` / `stop()`."""

    agent_id = "orchestra-001"

    @property
    def running(self) -> bool:
        return bool(orchestra_scheduler._running)  # type: ignore[attr-defined]

    @property
    def cycle_count(self) -> int:
        return getattr(orchestra_scheduler, "_cycles", 0)

    def start(self) -> None:
        try:
            bootstrap_swarm(start_scheduler=True)
        except Exception:  # noqa: BLE001
            log.exception("[Orchestra.start] bootstrap failed")

    def stop(self) -> None:
        try:
            orchestra_scheduler.stop()
        except Exception:  # noqa: BLE001
            log.debug("[Orchestra.stop] failed", exc_info=True)


orchestra = OrchestraAgentFacade()
