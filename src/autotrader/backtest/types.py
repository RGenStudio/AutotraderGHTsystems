"""Backtest trade records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from autotrader.strategy.types import Side, Signal, StrategyId


@dataclass(slots=True)
class OpenPosition:
    signal: Signal
    entry_fill: float
    stop: float
    take_profit: float | None
    trail_atr_mult: float | None
    entry_bar: int
    extreme: float  # best price since entry (high for long, low for short)
    risk_distance: float

    @property
    def side(self) -> Side:
        return self.signal.side

    @property
    def strategy(self) -> StrategyId:
        return self.signal.strategy


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    strategy: StrategyId
    side: Side
    entry_time: datetime
    exit_time: datetime
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    stop_price: float
    pnl: float
    pnl_r: float
    reason: str
    fees: float = 0.0
    meta: dict[str, float] = field(default_factory=dict)
