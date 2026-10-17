"""Engine up/down heartbeat → ``system_events``."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from autotrader.journal.api import TradeJournal

logger = logging.getLogger(__name__)

EVENT_ENGINE_UP = "engine_up"
EVENT_ENGINE_DOWN = "engine_down"
EVENT_HEARTBEAT = "heartbeat"


class HeartbeatRecorder:
    """
    Record engine lifecycle and periodic heartbeats into the trade journal.

    Downtime must be visible in ``system_events`` so paper quality is disclosed
    (local-run rules: downtime does not count as continuous paper silently).
    """

    def __init__(
        self,
        journal: TradeJournal,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._journal = journal
        self._clock = clock or (lambda: datetime.now(UTC))
        self._up = False

    @property
    def is_up(self) -> bool:
        return self._up

    def mark_up(self, *, message: str = "engine started", payload: dict | None = None) -> int:
        self._up = True
        event_id = self._journal.record_system_event(
            event_type=EVENT_ENGINE_UP,
            message=message,
            payload=payload or {"status": "up"},
            created_at=self._clock(),
        )
        logger.info("engine_up id=%s %s", event_id, message)
        return event_id

    def mark_down(self, *, message: str = "engine stopped", payload: dict | None = None) -> int:
        self._up = False
        event_id = self._journal.record_system_event(
            event_type=EVENT_ENGINE_DOWN,
            message=message,
            payload=payload or {"status": "down"},
            created_at=self._clock(),
        )
        logger.info("engine_down id=%s %s", event_id, message)
        return event_id

    def beat(self, *, message: str = "ok", payload: dict | None = None) -> int:
        """Periodic heartbeat while the engine is running."""
        event_id = self._journal.record_system_event(
            event_type=EVENT_HEARTBEAT,
            message=message,
            payload=payload or {"status": "up" if self._up else "unknown"},
            created_at=self._clock(),
        )
        logger.debug("heartbeat id=%s %s", event_id, message)
        return event_id
