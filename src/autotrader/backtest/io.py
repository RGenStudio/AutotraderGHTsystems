"""Load OHLC from CSV or synthetic fixtures (no MT5 required)."""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from autotrader.data.mock import generate_fixture_candles
from autotrader.data.types import Candle, Timeframe


def load_candles_csv(
    path: Path | str,
    *,
    symbol: str = "EURUSD",
    timeframe: Timeframe = Timeframe.H1,
) -> list[Candle]:
    """
    Load closed OHLC bars from CSV.

    Required columns (case-insensitive): time, open, high, low, close.
    Optional: volume. ``time`` parsed as UTC.
    """
    frame = pd.read_csv(path)
    cols = {c.lower(): c for c in frame.columns}
    required = ("time", "open", "high", "low", "close")
    missing = [c for c in required if c not in cols]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")

    candles: list[Candle] = []
    for _, row in frame.iterrows():
        raw_time = row[cols["time"]]
        ts = pd.Timestamp(raw_time)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        volume = float(row[cols["volume"]]) if "volume" in cols else 0.0
        candles.append(
            Candle(
                symbol=symbol.upper(),
                timeframe=timeframe,
                time=ts.to_pydatetime(),
                open=float(row[cols["open"]]),
                high=float(row[cols["high"]]),
                low=float(row[cols["low"]]),
                close=float(row[cols["close"]]),
                volume=volume,
            )
        )
    candles.sort(key=lambda c: c.time)
    return candles


def _pip(symbol: str) -> float:
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def _base(symbol: str) -> float:
    if symbol.upper() == "USDJPY":
        return 148.50
    if symbol.upper() == "EURUSD":
        return 1.0850
    return 1.0


def _candles_from_closes(
    closes: list[float],
    *,
    symbol: str,
    timeframe: Timeframe,
    end: datetime,
    pip: float,
    wide_bars: set[int] | None = None,
) -> list[Candle]:
    wide_bars = wide_bars or set()
    step = timedelta(hours=1 if timeframe is Timeframe.H1 else 4)
    candles: list[Candle] = []
    count = len(closes)
    for i, close_px in enumerate(closes):
        offset = count - 1 - i
        bar_time = end - offset * step
        open_px = closes[i - 1] if i else close_px
        pad = 15 * pip if i in wide_bars else 3 * pip
        high_px = max(open_px, close_px) + pad
        low_px = min(open_px, close_px) - pad
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


def _trend_closes(count: int, base: float, pip: float) -> tuple[list[float], set[int]]:
    """Directional legs + deep pullbacks (EMA crosses) and periodic wide bars (ATR)."""
    price = base
    closes: list[float] = []
    wide: set[int] = set()
    for i in range(count):
        phase = i % 120
        if phase < 70:
            price += 2.5 * pip
        elif phase < 95:
            price -= 3.0 * pip
        else:
            price += 1.2 * pip
        price += math.sin(i / 4.0) * 0.25 * pip
        closes.append(price)
        if phase == 72 or phase == 0:
            wide.add(i)
    return closes, wide


def _range_closes(count: int, base: float, pip: float) -> list[float]:
    """
    Mean-reverting OU path with occasional dumps/rallies so RSI tags extremes
    while ADX stays mostly < 20.
    """
    rng = random.Random(42)
    price = base
    closes: list[float] = []
    for i in range(count):
        if i % 70 < 6:
            price -= 6 * pip  # sharp dump → oversold
        elif i % 70 < 12:
            price += 6 * pip  # sharp rally → overbought
        else:
            price = price + 0.55 * (base - price) + rng.uniform(-3.5, 3.5) * pip
        closes.append(price)
    return closes


def synthetic_candles(
    *,
    symbol: str = "EURUSD",
    timeframe: Timeframe = Timeframe.H1,
    count: int = 500,
    scenario: str = "mixed",
) -> list[Candle]:
    """
    Build synthetic OHLC for CI / local backtests without MT5.

    Scenarios:
    - ``mixed``: mild trend + oscillation (default mock fixture)
    - ``trend``: directional legs with pullbacks (ADX high; A/B setups)
    - ``range``: mean-reverting path (ADX low; C setups)
    """
    if scenario == "mixed":
        return generate_fixture_candles(symbol, timeframe, count=count)

    if count < 60:
        raise ValueError("count must be >= 60")

    base = _base(symbol)
    pip = _pip(symbol)
    end = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)

    if scenario == "trend":
        closes, wide = _trend_closes(count, base, pip)
        return _candles_from_closes(
            closes, symbol=symbol, timeframe=timeframe, end=end, pip=pip, wide_bars=wide
        )
    if scenario == "range":
        closes = _range_closes(count, base, pip)
        return _candles_from_closes(
            closes, symbol=symbol, timeframe=timeframe, end=end, pip=pip
        )
    raise ValueError(f"unknown scenario: {scenario}")
