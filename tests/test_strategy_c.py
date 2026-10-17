"""Strategy C (mean reversion) signal cases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from autotrader.strategy.c_mean_reversion import evaluate_mean_reversion
from autotrader.strategy.types import Side, StrategyId


def _frame_from_rows(rows: list[dict]) -> pd.DataFrame:
    index = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(len(rows))]
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index, tz="UTC"))


def test_strategy_c_long_oversold() -> None:
    rows = [
        {
            "close": 1.08,
            "rsi14": 25.0,
            "bb_lower": 1.09,
            "bb_upper": 1.15,
            "bb_mid": 1.12,
            "atr14": 0.01,
            "adx14": 15.0,
        }
    ]
    sig = evaluate_mean_reversion(_frame_from_rows(rows), 0)
    assert sig is not None
    assert sig.strategy is StrategyId.C
    assert sig.side is Side.LONG
    assert sig.max_bars == 24
    assert sig.exit_mid_band is True
    assert sig.stop_price == 1.08 - 1.5 * 0.01


def test_strategy_c_short_overbought() -> None:
    rows = [
        {
            "close": 1.16,
            "rsi14": 75.0,
            "bb_lower": 1.09,
            "bb_upper": 1.15,
            "bb_mid": 1.12,
            "atr14": 0.01,
            "adx14": 15.0,
        }
    ]
    sig = evaluate_mean_reversion(_frame_from_rows(rows), 0)
    assert sig is not None
    assert sig.side is Side.SHORT


def test_strategy_c_no_signal_when_rsi_not_extreme() -> None:
    rows = [
        {
            "close": 1.08,
            "rsi14": 40.0,
            "bb_lower": 1.09,
            "bb_upper": 1.15,
            "bb_mid": 1.12,
            "atr14": 0.01,
            "adx14": 15.0,
        }
    ]
    assert evaluate_mean_reversion(_frame_from_rows(rows), 0) is None
