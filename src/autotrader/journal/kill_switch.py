"""Kill switch that mirrors state into the trade journal DB."""

from __future__ import annotations

from datetime import UTC, datetime

from autotrader.journal.api import TradeJournal
from autotrader.kill_switch import KillSwitch, KillSwitchState


class PersistentKillSwitch(KillSwitch):
    """
    Same interface as :class:`~autotrader.kill_switch.KillSwitch`, plus SQLite sync.

    Hydrates from ``kill_switch_state`` on init; engage/clear write the row and
    append a ``system_events`` entry.
    """

    def __init__(self, journal: TradeJournal) -> None:
        super().__init__()
        self._journal = journal
        self._hydrate()

    def _hydrate(self) -> None:
        state = self._journal.get_kill_switch_state()
        self._active = state.active
        self._reason = state.reason
        self._engaged_at = state.engaged_at

    def engage(self, reason: str, *, when: datetime | None = None) -> None:
        was_active = self._active
        super().engage(reason, when=when)
        if was_active:
            return
        snap = self.snapshot()
        self._journal.set_kill_switch_state(snap)
        self._journal.record_system_event(
            event_type="kill_switch_engage",
            message=snap.reason,
            payload={
                "active": snap.active,
                "reason": snap.reason,
                "engaged_at": snap.engaged_at.isoformat() if snap.engaged_at else None,
            },
            created_at=when or datetime.now(UTC),
        )

    def clear(self) -> None:
        was_active = self._active
        prior = self.snapshot()
        super().clear()
        if not was_active:
            return
        snap = KillSwitchState(active=False, reason="", engaged_at=None)
        self._journal.set_kill_switch_state(snap)
        self._journal.record_system_event(
            event_type="kill_switch_clear",
            message=prior.reason or "cleared",
            payload={"prior_reason": prior.reason},
        )
