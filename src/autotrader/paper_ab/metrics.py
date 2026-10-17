"""Arm-level metrics for paper A/B (trades, expectancy, max DD, bad-JSON rate)."""

from __future__ import annotations

from datetime import datetime

from autotrader.paper_ab.types import ArmMetrics, ArmName, ClosedPaperTrade


def compute_arm_metrics(
    *,
    arm: ArmName,
    trades: list[ClosedPaperTrade],
    starting_equity: float,
    agent4_calls: int = 0,
    bad_json_count: int = 0,
    cycles_seen: int = 0,
    signals_seen: int = 0,
    entries_approved: int = 0,
    entries_rejected: int = 0,
    first_time: datetime | None = None,
    last_time: datetime | None = None,
) -> ArmMetrics:
    if starting_equity <= 0:
        raise ValueError("starting_equity must be > 0")

    wins = [t for t in trades if t.pnl_r > 0]
    losses = [t for t in trades if t.pnl_r <= 0]
    n = len(trades)
    win_rate = (len(wins) / n) if n else 0.0
    avg_win_r = (sum(t.pnl_r for t in wins) / len(wins)) if wins else 0.0
    avg_loss_r = (sum(abs(t.pnl_r) for t in losses) / len(losses)) if losses else 0.0
    if avg_loss_r > 0:
        reward_risk = avg_win_r / avg_loss_r
    else:
        reward_risk = avg_win_r if avg_win_r > 0 else 0.0
    expectancy_r = (sum(t.pnl_r for t in trades) / n) if n else 0.0
    net_pnl = sum(t.pnl for t in trades)

    equity = starting_equity
    peak = equity
    max_dd = 0.0
    max_dd_pct = 0.0
    for trade in trades:
        equity += trade.pnl
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
        if peak > 0:
            max_dd_pct = max(max_dd_pct, dd / peak)

    bad_rate = (bad_json_count / agent4_calls) if agent4_calls > 0 else 0.0
    weeks = 0.0
    if first_time is not None and last_time is not None and last_time >= first_time:
        weeks = (last_time - first_time).total_seconds() / (7 * 24 * 3600)

    return ArmMetrics(
        arm=arm,
        trades=n,
        wins=len(wins),
        losses=len(losses),
        win_rate=win_rate,
        avg_win_r=avg_win_r,
        avg_loss_r=avg_loss_r,
        reward_risk=reward_risk,
        expectancy_r=expectancy_r,
        net_pnl=net_pnl,
        net_return_pct=(equity - starting_equity) / starting_equity,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        equity_end=equity,
        starting_equity=starting_equity,
        agent4_calls=agent4_calls,
        bad_json_count=bad_json_count,
        bad_json_rate=bad_rate,
        cycles_seen=cycles_seen,
        signals_seen=signals_seen,
        entries_approved=entries_approved,
        entries_rejected=entries_rejected,
        calendar_weeks=weeks,
    )
