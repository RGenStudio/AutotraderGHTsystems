"""Kill-switch flag — in-memory stub (config/db backends later)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class KillSwitchState:
    """Snapshot of the kill switch for journaling / dashboards."""

    active: bool
    reason: str = ""
    engaged_at: datetime | None = None


@dataclass
class KillSwitch:
    """
    Process-local kill switch checked every Risk Engine cycle.

    Engage pauses new entries until a human clears. Weekly DD / reconcile
    mismatch should engage this flag. Persistence (SQLite) can wrap the same
    interface later without changing the Risk Engine call sites.
    """

    _active: bool = False
    _reason: str = ""
    _engaged_at: datetime | None = field(default=None, repr=False)

    def is_active(self) -> bool:
        """Return True when new entries must be blocked."""
        return self._active

    def check(self) -> bool:
        """Alias used at the start of every engine cycle."""
        return self.is_active()

    def engage(self, reason: str, *, when: datetime | None = None) -> None:
        """Arm the kill switch (idempotent if already active)."""
        if not reason.strip():
            raise ValueError("kill switch reason must be non-empty")
        if self._active:
            return
        self._active = True
        self._reason = reason.strip()
        self._engaged_at = when or datetime.now(UTC)

    def clear(self) -> None:
        """Human reset after review — only call intentionally."""
        self._active = False
        self._reason = ""
        self._engaged_at = None

    def snapshot(self) -> KillSwitchState:
        return KillSwitchState(
            active=self._active,
            reason=self._reason,
            engaged_at=self._engaged_at,
        )
