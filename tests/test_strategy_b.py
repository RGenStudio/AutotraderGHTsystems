"""Strategy B (breakout) signal cases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from autotrader.strategy.b_breakout import evaluate_breakout
from autotrader.strategy.types import Side, StrategyId


def _frame_from_rows(rows: list[dict]) -> pd.DataFrame:
    index = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(len(rows))]
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index, tz="UTC"))


def test_strategy_b_long_breakout() -> None:
    rows = [
        {
            "close": 1.10,
            "atr14": 0.02,
            "atr50_sma": 0.01,
            "high_20_prior": 1.11,
            "low_20_prior": 1.05,
            "adx14": 30.0,
        },
        {
            "close": 1.12,
            "atr14": 0.02,
            "atr50_sma": 0.01,
            "high_20_prior": 1.11,
            "low_20_prior": 1.05,
            "adx14": 30.0,
        },
    ]
    sig = evaluate_breakout(_frame_from_rows(rows), 1)
    assert sig is not None
    assert sig.strategy is StrategyId.B
    assert sig.side is Side.LONG
    assert sig.stop_price == 1.12 - 1.5 * 0.02
    assert sig.take_profit == 1.12 + 2.0 * (1.5 * 0.02)


def test_strategy_b_short_breakout() -> None:
    rows = [
        {
            "close": 1.10,
            "atr14": 0.02,
            "atr50_sma": 0.01,
            "high_20_prior": 1.20,
            "low_20_prior": 1.09,
            "adx14": 30.0,
        },
        {
            "close": 1.08,
            "atr14": 0.02,
            "atr50_sma": 0.01,
            "high_20_prior": 1.20,
            "low_20_prior": 1.09,
            "adx14": 30.0,
        },
    ]
    sig = evaluate_breakout(_frame_from_rows(rows), 1)
    assert sig is not None
    assert sig.side is Side.SHORT


def test_strategy_b_requires_atr_above_average() -> None:
    rows = [
        {
            "close": 1.10,
            "atr14": 0.01,
            "atr50_sma": 0.02,
            "high_20_prior": 1.11,
            "low_20_prior": 1.05,
            "adx14": 30.0,
        },
        {
            "close": 1.12,
            "atr14": 0.01,
            "atr50_sma": 0.02,
            "high_20_prior": 1.11,
            "low_20_prior": 1.05,
            "adx14": 30.0,
        },
    ]
    assert evaluate_breakout(_frame_from_rows(rows), 1) is None
