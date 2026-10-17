"""Market data provider protocol (MT5 or mock)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from autotrader.data.types import Candle, Timeframe


@runtime_checkable
class MarketDataProvider(Protocol):
    """Fetch closed H1/H4 candles for configured Forex symbols."""

    def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        count: int = 200,
    ) -> list[Candle]:
        """
        Return the most recent ``count`` **closed** candles (oldest → newest).

        Implementations must not include the currently forming bar.
        """
        ...

    def available_symbols(self) -> list[str]:
        """Symbols this provider can serve (subset of project symbols)."""
        ...
