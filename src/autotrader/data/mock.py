"""Deterministic mock/fixture market data for Linux CI and local tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from autotrader.data.types import Candle, Timeframe

# Default symbols match project config.
DEFAULT_SYMBOLS = ("EURUSD", "USDJPY")

_TF_DELTA = {
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
}

# Anchor so fixtures are stable across runs (a Monday 12:00 UTC).
_ANCHOR = datetime(2024, 1, 8, 12, 0, tzinfo=UTC)


def _base_price(symbol: str) -> float:
    if symbol.upper() == "EURUSD":
        return 1.0850
    if symbol.upper() == "USDJPY":
        return 148.50
    return 1.0


def generate_fixture_candles(
    symbol: str,
    timeframe: Timeframe,
    *,
    count: int = 200,
    end: datetime | None = None,
) -> list[Candle]:
    """
    Build a synthetic OHLC series with a mild trend + oscillation.

    Gaps are not inserted by default (continuous bars) so indicator tests stay stable.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    if timeframe not in _TF_DELTA:
        raise ValueError(f"unsupported timeframe: {timeframe}")

    step = _TF_DELTA[timeframe]
    last_open = end or _ANCHOR
    if last_open.tzinfo is None:
        last_open = last_open.replace(tzinfo=UTC)
    else:
        last_open = last_open.astimezone(UTC)

    # last_open is the open time of the most recent *closed* bar.
    base = _base_price(symbol)
    pip = 0.0001 if "JPY" not in symbol.upper() else 0.01
    candles: list[Candle] = []

    for i in range(count):
        # Oldest first: bar index 0 is count-1 steps before last_open.
        offset = count - 1 - i
        bar_time = last_open - offset * step
        # Mild upward drift + sine-like wobble from index.
        drift = i * pip * 0.5
        wobble = ((i % 17) - 8) * pip
        open_px = base + drift + wobble
        close_px = open_px + ((i % 5) - 2) * pip
        high_px = max(open_px, close_px) + 3 * pip
        low_px = min(open_px, close_px) - 3 * pip
        candles.append(
            Candle(
                symbol=symbol.upper(),
                timeframe=timeframe,
                time=bar_time,
                open=round(open_px, 5),
                high=round(high_px, 5),
                low=round(low_px, 5),
                close=round(close_px, 5),
                volume=float(100 + (i % 40)),
            )
        )
    return candles


class MockMarketDataProvider:
    """In-memory fixture backend — used when MetaTrader5 is unavailable."""

    def __init__(
        self,
        symbols: tuple[str, ...] | list[str] = DEFAULT_SYMBOLS,
        *,
        end: datetime | None = None,
    ) -> None:
        self._symbols = tuple(s.upper() for s in symbols)
        self._end = end
        self._cache: dict[tuple[str, Timeframe], list[Candle]] = {}
        for symbol in self._symbols:
            for tf in (Timeframe.H1, Timeframe.H4):
                self._cache[(symbol, tf)] = generate_fixture_candles(
                    symbol, tf, count=300, end=end
                )

    def available_symbols(self) -> list[str]:
        return list(self._symbols)

    def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        count: int = 200,
    ) -> list[Candle]:
        key = (symbol.upper(), timeframe)
        if key not in self._cache:
            raise KeyError(f"mock provider has no data for {symbol} {timeframe}")
        series = self._cache[key]
        if count > len(series):
            raise ValueError(f"requested {count} candles but fixture has {len(series)}")
        return list(series[-count:])
