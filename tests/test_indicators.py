"""Indicator unit tests — EMA / RSI / ATR / ADX (Wilder-style)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from autotrader.data.mock import generate_fixture_candles
from autotrader.data.types import Timeframe
from autotrader.indicators import adx, atr, candles_to_frame, ema, rsi
from autotrader.indicators.core import wilder_rma


def test_candles_to_frame_and_ema_on_fixtures() -> None:
    candles = generate_fixture_candles("EURUSD", Timeframe.H1, count=220)
    frame = candles_to_frame(candles)
    assert len(frame) == 220
    e20 = ema(frame["close"], 20)
    e50 = ema(frame["close"], 50)
    e200 = ema(frame["close"], 200)
    assert e20.notna().sum() >= 200
    assert e50.iloc[-1] > 0
    assert e200.iloc[-1] > 0
    # Early bars before period are NaN
    assert math.isnan(e20.iloc[0])


def test_ema_matches_manual_two_period() -> None:
    close = pd.Series([10.0, 11.0, 12.0, 13.0])
    result = ema(close, period=2)
    # k = 2/(2+1) = 2/3; first valid at index 1 (min_periods=2) uses ewm seed
    assert result.iloc[0] != result.iloc[0]  # NaN
    assert result.iloc[-1] == pytest.approx(
        close.ewm(span=2, adjust=False, min_periods=2).mean().iloc[-1]
    )


def test_rsi_bounds_on_trending_series() -> None:
    # Strictly rising closes → RSI near 100 after warmup
    close = pd.Series([float(i) for i in range(1, 60)])
    values = rsi(close, period=14)
    assert values.iloc[-1] > 70
    assert values.max() <= 100.0 + 1e-9
    assert values.min() >= 0.0 - 1e-9 or math.isnan(values.min())


def test_rsi_falling_series_is_low() -> None:
    close = pd.Series([float(60 - i) for i in range(60)])
    values = rsi(close, period=14)
    assert values.iloc[-1] < 30


def test_atr_positive_on_fixtures() -> None:
    candles = generate_fixture_candles("USDJPY", Timeframe.H4, count=80)
    frame = candles_to_frame(candles)
    values = atr(frame["high"], frame["low"], frame["close"], period=14)
    assert values.dropna().iloc[-1] > 0
    assert values.notna().sum() >= 50


def test_adx_columns_and_range() -> None:
    candles = generate_fixture_candles("EURUSD", Timeframe.H1, count=120)
    frame = candles_to_frame(candles)
    out = adx(frame["high"], frame["low"], frame["close"], period=14)
    assert list(out.columns) == ["adx", "plus_di", "minus_di"]
    last = out.dropna().iloc[-1]
    assert 0 <= last["adx"] <= 100
    assert 0 <= last["plus_di"] <= 100
    assert 0 <= last["minus_di"] <= 100


def test_wilder_rma_stable() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    out = wilder_rma(series, 3)
    assert out.iloc[-1] == pytest.approx(
        series.ewm(alpha=1 / 3, adjust=False, min_periods=3).mean().iloc[-1]
    )


def test_strategy_periods_used_in_brief() -> None:
    """Brief strategies reference EMA20/50/200, RSI(14), ATR(14), ADX(14)."""
    candles = generate_fixture_candles("EURUSD", Timeframe.H1, count=250)
    frame = candles_to_frame(candles)
    assert ema(frame["close"], 20).iloc[-1] > 0
    assert ema(frame["close"], 50).iloc[-1] > 0
    assert ema(frame["close"], 200).iloc[-1] > 0
    assert 0 <= rsi(frame["close"], 14).iloc[-1] <= 100
    assert atr(frame["high"], frame["low"], frame["close"], 14).iloc[-1] > 0
    assert adx(frame["high"], frame["low"], frame["close"], 14)["adx"].iloc[-1] >= 0
