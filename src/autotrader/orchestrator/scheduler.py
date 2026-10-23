"""Scheduler hook for H1 cycles — testable with a fake clock."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from autotrader.db.engine import (
    DB_RETRY_SECONDS,
    is_database_connectivity_error,
    safe_exception_text,
)
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
        Loop with real/fake sleep until :meth:`stop`, Ctrl+C, or ``max_cycles``.

        Prefer :meth:`run_until` in tests. ``max_cycles`` guards CI / smoke runs.
        Production CLI passes ``time.sleep``; default ``sleep`` is a no-op for tests.
        """
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("max_cycles must be >= 1 when set")

        if self.on_start is not None:
            self.on_start()
        results: list[CycleResult] = []
        self._running = True
        cycles = 0
        announced_up = False
        try:
            while self._running:
                if not announced_up:
                    try:
                        self.orchestrator.heartbeat.mark_up(message="scheduler_start")
                        announced_up = True
                    except Exception as exc:  # noqa: BLE001 — retry only connectivity
                        if not is_database_connectivity_error(exc):
                            raise
                        self._log_database_retry(exc)
                        self._dispose_journal_pool()
                        results.append(self._unreachable_result(exc))
                        cycles += 1
                        if max_cycles is not None and cycles >= max_cycles:
                            break
                        self._sleep_database_retry()
                        continue
                try:
                    results.append(self.run_once())
                except Exception as exc:  # noqa: BLE001 — retry only connectivity
                    if not is_database_connectivity_error(exc):
                        raise
                    self._log_database_retry(exc)
                    self._dispose_journal_pool()
                    results.append(self._unreachable_result(exc))
                    cycles += 1
                    if max_cycles is not None and cycles >= max_cycles:
                        break
                    self._sleep_database_retry()
                    continue
                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break
                self.sleep(self.interval.total_seconds())
        except KeyboardInterrupt:
            logger.info("scheduler interrupted (Ctrl+C) after %s cycle(s)", cycles)
            self._running = False
        finally:
            self._running = False
            self._mark_down_best_effort()
            if self.on_stop is not None:
                self.on_stop()
        return results

    def _sleep_database_retry(self) -> None:
        """Wait a short interval — not a full H1 bar — after a dropped database."""
        delay = DB_RETRY_SECONDS
        step = self.interval.total_seconds()
        if step > 0:
            delay = min(delay, step)
        self.sleep(delay)

    def _log_database_retry(self, exc: BaseException) -> None:
        logger.error(
            "Journal database unreachable (%s). "
            "DATABASE_URL stays in effect — not falling back to SQLite. "
            "Retrying next cycle.",
            safe_exception_text(exc),
        )

    def _unreachable_result(self, exc: BaseException) -> CycleResult:
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        else:
            now = now.astimezone(UTC)
        return CycleResult(
            status="error",
            reason="database_unreachable",
            now=now,
            mode=self.orchestrator.config.mode,
            errors=(safe_exception_text(exc),),
        )

    def _dispose_journal_pool(self) -> None:
        dispose = getattr(self.orchestrator.journal, "dispose", None)
        if not callable(dispose):
            return
        try:
            dispose()
        except Exception as exc:  # noqa: BLE001 — pool cleanup must not kill the loop
            logger.error("journal pool dispose failed: %s", safe_exception_text(exc))

    def _mark_down_best_effort(self) -> None:
        try:
            self.orchestrator.heartbeat.mark_down(message="scheduler_stop")
        except Exception as exc:  # noqa: BLE001 — shutdown must not mask the loop result
            if is_database_connectivity_error(exc):
                logger.error(
                    "could not record engine_down: %s",
                    safe_exception_text(exc),
                )
            else:
                logger.error("could not record engine_down: %s", safe_exception_text(exc))
