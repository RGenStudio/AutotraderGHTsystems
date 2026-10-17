"""Shared candle / timeframe types for the data layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Timeframe(StrEnum):
    H1 = "H1"
    H4 = "H4"


@dataclass(frozen=True, slots=True)
class Candle:
    """One OHLCV bar. ``time`` is the bar open time in UTC (closed bars only)."""

    symbol: str
    timeframe: Timeframe
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open, close, and high")
