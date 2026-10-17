"""M3 kill-switch flag tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from autotrader.kill_switch import KillSwitch


def test_engage_check_clear_cycle() -> None:
    ks = KillSwitch()
    assert ks.check() is False
    ks.engage("manual_test", when=datetime(2026, 10, 17, 12, 0, tzinfo=UTC))
    assert ks.is_active() is True
    snap = ks.snapshot()
    assert snap.active is True
    assert snap.reason == "manual_test"
    assert snap.engaged_at is not None
    ks.clear()
    assert ks.check() is False
    assert ks.snapshot().reason == ""


def test_engage_requires_reason_and_is_idempotent() -> None:
    ks = KillSwitch()
    with pytest.raises(ValueError):
        ks.engage("  ")
    ks.engage("first")
    ks.engage("second")  # ignored while active
    assert ks.snapshot().reason == "first"
