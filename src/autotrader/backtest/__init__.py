"""Backtester — closed-bar, no look-ahead, configurable costs."""

from autotrader.backtest.costs import CostModel
from autotrader.backtest.engine import Backtester, BacktestResult
from autotrader.backtest.metrics import BacktestReport, compute_report

__all__ = [
    "BacktestReport",
    "BacktestResult",
    "Backtester",
    "CostModel",
    "compute_report",
]
