"""M0 risk default and pure-gate tests."""

from __future__ import annotations

import pytest

from autotrader.risk import check_new_entry, default_risk_limits, position_size_risk_pct


def test_default_risk_limits_match_project_lock() -> None:
    limits = default_risk_limits()
    assert limits.max_risk_per_trade_pct == 0.5
    assert limits.max_daily_loss_pct == 2.0
    assert limits.max_weekly_drawdown_pct == 5.0
    assert limits.max_open_positions == 2


def test_check_new_entry_allows_within_limits() -> None:
    decision = check_new_entry(
        limits=default_risk_limits(),
        open_positions=1,
        daily_loss_pct=0.0,
        weekly_drawdown_pct=0.0,
        requested_risk_pct=0.5,
    )
    assert decision.allowed is True
    assert decision.reason == "ok"


def test_check_new_entry_rejects_max_open() -> None:
    decision = check_new_entry(
        limits=default_risk_limits(),
        open_positions=2,
        daily_loss_pct=0.0,
        weekly_drawdown_pct=0.0,
        requested_risk_pct=0.5,
    )
    assert decision.allowed is False
    assert decision.reason == "max_open_positions"


def test_check_new_entry_rejects_daily_and_weekly() -> None:
    limits = default_risk_limits()
    daily = check_new_entry(
        limits=limits,
        open_positions=0,
        daily_loss_pct=2.0,
        weekly_drawdown_pct=0.0,
        requested_risk_pct=0.5,
    )
    weekly = check_new_entry(
        limits=limits,
        open_positions=0,
        daily_loss_pct=0.0,
        weekly_drawdown_pct=5.0,
        requested_risk_pct=0.5,
    )
    assert daily.reason == "max_daily_loss"
    assert weekly.reason == "max_weekly_drawdown"


def test_check_new_entry_rejects_over_risk_and_kill_switch() -> None:
    limits = default_risk_limits()
    over = check_new_entry(
        limits=limits,
        open_positions=0,
        daily_loss_pct=0.0,
        weekly_drawdown_pct=0.0,
        requested_risk_pct=0.51,
    )
    kill = check_new_entry(
        limits=limits,
        open_positions=0,
        daily_loss_pct=0.0,
        weekly_drawdown_pct=0.0,
        requested_risk_pct=0.5,
        kill_switch=True,
    )
    assert over.reason == "requested_risk_above_cap"
    assert kill.reason == "kill_switch_active"


def test_position_size_risk_pct() -> None:
    # equity 10_000, 0.5% risk => 50; stop 0.0010 => 50_000 units
    size = position_size_risk_pct(10_000, 0.0010, 0.5)
    assert size == pytest.approx(50_000.0)
