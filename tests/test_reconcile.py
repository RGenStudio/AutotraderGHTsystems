"""M3 startup reconcile — mismatch pauses via kill switch."""

from __future__ import annotations

from autotrader.execution.types import Position
from autotrader.kill_switch import KillSwitch
from autotrader.reconcile import reconcile_positions


def _pos(symbol: str, ticket: str, side: str = "long") -> Position:
    return Position(
        symbol=symbol,
        side=side,
        volume=0.1,
        entry_price=1.0,
        ticket=ticket,
    )


def test_reconcile_ok_when_both_flat() -> None:
    ks = KillSwitch()
    result = reconcile_positions(local=[], remote=[], kill_switch=ks)
    assert result.ok is True
    assert result.paused is False
    assert ks.is_active() is False


def test_reconcile_ok_when_matching() -> None:
    ks = KillSwitch()
    local = [_pos("EURUSD", "t1")]
    remote = [_pos("EURUSD", "t1")]
    result = reconcile_positions(local=local, remote=remote, kill_switch=ks)
    assert result.ok is True
    assert result.paused is False


def test_reconcile_mismatch_pauses() -> None:
    ks = KillSwitch()
    local = [_pos("EURUSD", "local-1")]
    remote = [_pos("EURUSD", "broker-9")]
    result = reconcile_positions(local=local, remote=remote, kill_switch=ks)
    assert result.ok is False
    assert result.paused is True
    assert result.reason == "reconcile_mismatch"
    assert ks.is_active() is True
    assert ks.snapshot().reason == "reconcile_mismatch"


def test_reconcile_count_mismatch() -> None:
    ks = KillSwitch()
    local = [_pos("EURUSD", "t1"), _pos("USDJPY", "t2")]
    remote = [_pos("EURUSD", "t1")]
    result = reconcile_positions(local=local, remote=remote, kill_switch=ks)
    assert result.paused is True
    assert "USDJPY" in result.mismatched_symbols
