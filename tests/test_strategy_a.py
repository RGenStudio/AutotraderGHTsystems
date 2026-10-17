"""Strategy A (trend) signal cases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from autotrader.strategy.a_trend import evaluate_trend
from autotrader.strategy.types import Side, StrategyId


def _frame_from_rows(rows: list[dict]) -> pd.DataFrame:
    index = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(len(rows))]
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index, tz="UTC"))


def test_strategy_a_long_on_ema_cross_above_ema200() -> None:
    # prev: ema20 <= ema50; now: ema20 > ema50; close > ema200
    rows = [
        {
            "close": 1.10,
            "ema20": 1.09,
            "ema50": 1.10,
            "ema200": 1.05,
            "atr14": 0.01,
            "adx14": 30.0,
        },
        {
            "close": 1.12,
            "ema20": 1.11,
            "ema50": 1.10,
            "ema200": 1.05,
            "atr14": 0.01,
            "adx14": 32.0,
        },
    ]
    frame = _frame_from_rows(rows)
    sig = evaluate_trend(frame, 1)
    assert sig is not None
    assert sig.strategy is StrategyId.A
    assert sig.side is Side.LONG
    assert sig.stop_price == 1.12 - 2.0 * 0.01
    assert sig.trail_atr_mult == 2.5


def test_strategy_a_short_on_ema_cross_below_ema200() -> None:
    rows = [
        {
            "close": 1.10,
            "ema20": 1.11,
            "ema50": 1.10,
            "ema200": 1.15,
            "atr14": 0.01,
            "adx14": 30.0,
        },
        {
            "close": 1.08,
            "ema20": 1.09,
            "ema50": 1.10,
            "ema200": 1.15,
            "atr14": 0.01,
            "adx14": 32.0,
        },
    ]
    frame = _frame_from_rows(rows)
    sig = evaluate_trend(frame, 1)
    assert sig is not None
    assert sig.side is Side.SHORT
    assert sig.stop_price == 1.08 + 2.0 * 0.01


def test_strategy_a_no_signal_without_cross() -> None:
    rows = [
        {
            "close": 1.12,
            "ema20": 1.11,
            "ema50": 1.10,
            "ema200": 1.05,
            "atr14": 0.01,
            "adx14": 30.0,
        },
        {
            "close": 1.13,
            "ema20": 1.12,
            "ema50": 1.10,
            "ema200": 1.05,
            "atr14": 0.01,
            "adx14": 30.0,
        },
    ]
    assert evaluate_trend(_frame_from_rows(rows), 1) is None


def test_strategy_a_rejects_long_below_ema200() -> None:
    rows = [
        {
            "close": 1.04,
            "ema20": 1.09,
            "ema50": 1.10,
            "ema200": 1.05,
            "atr14": 0.01,
            "adx14": 30.0,
        },
        {
            "close": 1.04,
            "ema20": 1.11,
            "ema50": 1.10,
            "ema200": 1.05,
            "atr14": 0.01,
            "adx14": 30.0,
        },
    ]
    assert evaluate_trend(_frame_from_rows(rows), 1) is None
