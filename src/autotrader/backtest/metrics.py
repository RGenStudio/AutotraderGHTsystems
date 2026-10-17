"""Backtest performance metrics: win rate, R:R, max DD, expectancy."""

from __future__ import annotations

from dataclasses import dataclass

from autotrader.backtest.types import ClosedTrade


@dataclass(frozen=True, slots=True)
class BacktestReport:
    trades: int
    wins: int
    losses: int
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    reward_risk: float
    expectancy_r: float
    net_pnl: float
    max_drawdown: float
    max_drawdown_pct: float
    equity_end: float

    def summary_lines(self) -> list[str]:
        return [
            f"trades={self.trades}",
            f"win_rate={self.win_rate:.2%}",
            f"avg_win_R={self.avg_win_r:.3f}",
            f"avg_loss_R={self.avg_loss_r:.3f}",
            f"R:R={self.reward_risk:.3f}",
            f"expectancy_R={self.expectancy_r:.3f}",
            f"net_pnl={self.net_pnl:.6f}",
            f"max_DD={self.max_drawdown:.6f} ({self.max_drawdown_pct:.2%})",
            f"equity_end={self.equity_end:.6f}",
        ]


def compute_report(
    closed: list[ClosedTrade],
    *,
    starting_equity: float = 1.0,
) -> BacktestReport:
    if starting_equity <= 0:
        raise ValueError("starting_equity must be > 0")

    wins = [t for t in closed if t.pnl_r > 0]
    losses = [t for t in closed if t.pnl_r <= 0]
    n = len(closed)
    win_rate = (len(wins) / n) if n else 0.0
    avg_win_r = (sum(t.pnl_r for t in wins) / len(wins)) if wins else 0.0
    avg_loss_r = (sum(abs(t.pnl_r) for t in losses) / len(losses)) if losses else 0.0
    if avg_loss_r > 0:
        reward_risk = avg_win_r / avg_loss_r
    else:
        reward_risk = avg_win_r if avg_win_r > 0 else 0.0
    expectancy_r = (sum(t.pnl_r for t in closed) / n) if n else 0.0
    net_pnl = sum(t.pnl for t in closed)

    equity = starting_equity
    peak = equity
    max_dd = 0.0
    max_dd_pct = 0.0
    for trade in closed:
        equity += trade.pnl
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
        if peak > 0:
            max_dd_pct = max(max_dd_pct, dd / peak)

    return BacktestReport(
        trades=n,
        wins=len(wins),
        losses=len(losses),
        win_rate=win_rate,
        avg_win_r=avg_win_r,
        avg_loss_r=avg_loss_r,
        reward_risk=reward_risk,
        expectancy_r=expectancy_r,
        net_pnl=net_pnl,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        equity_end=equity,
    )
