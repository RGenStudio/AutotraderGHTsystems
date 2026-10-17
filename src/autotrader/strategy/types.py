"""Shared types for Strategy Engine candidate signals (code-only; no AI)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Side(StrEnum):
    LONG = "long"
    SHORT = "short"


class StrategyId(StrEnum):
    A = "A"  # trend following
    B = "B"  # breakout
    C = "C"  # mean reversion


class Regime(StrEnum):
    """ADX regime gate (brief §4)."""

    TREND = "trend"  # ADX > 25 → strategies A or B
    RANGE = "range"  # ADX < 20 → strategy C
    NO_TRADE = "no_trade"  # ADX 20–25


@dataclass(frozen=True, slots=True)
class Signal:
    """
    Candidate entry produced by the Strategy Engine on a *closed* bar.

    ``bar_index`` indexes the OHLC series (0 = oldest). Entry uses that bar's
    close (plus configurable costs in the backtester). AI must not invent signals.
    """

    strategy: StrategyId
    side: Side
    bar_index: int
    bar_time: datetime
    entry_price: float
    stop_price: float
    atr: float
    take_profit: float | None = None
    trail_atr_mult: float | None = None
    max_bars: int | None = None
    exit_mid_band: bool = False
    reason: str = ""

    @property
    def risk_distance(self) -> float:
        """1R = absolute distance from entry to stop."""
        return abs(self.entry_price - self.stop_price)
