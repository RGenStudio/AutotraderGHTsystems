"""Scheduler hook for H1 cycles — testable with a fake clock."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from autotrader.orchestrator.cycle import CycleResult, Orchestrator

logger = logging.getLogger(__name__)


class CycleScheduler(Protocol):
    """Minimal scheduler interface (APScheduler-compatible shape)."""

    def run_once(self, *, now: datetime | None = None) -> CycleResult:
        """Execute a single orchestrator cycle."""
        ...

    def run_until(
        self,
        *,
        stop_at: datetime,
        start: datetime | None = None,
        interval: timedelta | None = None,
    ) -> list[CycleResult]:
        """Advance a fake/real clock and run cycles until ``stop_at``."""
        ...


@dataclass
class SimpleIntervalScheduler:
    """
    Simple interval loop — no APScheduler dependency.

    Injectable ``clock`` / ``sleep`` make unit tests deterministic with a fake
    clock and no real waiting. Production can pass ``time.sleep``.
    """

    orchestrator: Orchestrator
    interval: timedelta = field(default_factory=lambda: timedelta(hours=1))
    clock: Callable[[], datetime] = field(default_factory=lambda: (lambda: datetime.now(UTC)))
    sleep: Callable[[float], None] = field(default_factory=lambda: (lambda _s: None))
    on_start: Callable[[], None] | None = None
    on_stop: Callable[[], None] | None = None
    _running: bool = field(default=False, init=False, repr=False)

    def run_once(self, *, now: datetime | None = None) -> CycleResult:
        instant = now
        if instant is None:
            instant = self.clock()
        return self.orchestrator.run_cycle(now=instant)

    def run_until(
        self,
        *,
        stop_at: datetime,
        start: datetime | None = None,
        interval: timedelta | None = None,
    ) -> list[CycleResult]:
        """
        Run cycles from ``start`` (or clock()) stepping by ``interval`` until
        ``stop_at`` (exclusive of times >= stop_at after the last eligible tick).
        """
        step = interval or self.interval
        cursor = start or self.clock()
        if cursor.tzinfo is None:
            cursor = cursor.replace(tzinfo=UTC)
        if stop_at.tzinfo is None:
            stop_at = stop_at.replace(tzinfo=UTC)

        if self.on_start is not None:
            self.on_start()
        self.orchestrator.heartbeat.mark_up(message="scheduler_start")

        results: list[CycleResult] = []
        self._running = True
        try:
            while self._running and cursor < stop_at:
                results.append(self.run_once(now=cursor))
                cursor = cursor + step
                # Fake clock tests: sleep is a no-op; real runs may wait.
                remaining = (stop_at - cursor).total_seconds()
                if remaining > 0 and step.total_seconds() > 0:
                    self.sleep(min(step.total_seconds(), remaining))
        finally:
            self._running = False
            self.orchestrator.heartbeat.mark_down(message="scheduler_stop")
            if self.on_stop is not None:
                self.on_stop()
        return results

    def stop(self) -> None:
        """Request cooperative stop of :meth:`run_until` / :meth:`run_forever`."""
        self._running = False

    def run_forever(self, *, max_cycles: int | None = None) -> list[CycleResult]:
        """
        Loop with real/fake sleep until :meth:`stop` or ``max_cycles``.

        Prefer :meth:`run_until` in tests. ``max_cycles`` guards CI / smoke runs.
        """
        if self.on_start is not None:
            self.on_start()
        self.orchestrator.heartbeat.mark_up(message="scheduler_start")
        results: list[CycleResult] = []
        self._running = True
        cycles = 0
        try:
            while self._running:
                results.append(self.run_once())
                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break
                self.sleep(self.interval.total_seconds())
        finally:
            self._running = False
            self.orchestrator.heartbeat.mark_down(message="scheduler_stop")
            if self.on_stop is not None:
                self.on_stop()
        return results
