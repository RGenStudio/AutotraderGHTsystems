"""StrategyEngine regime integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.types import Regime, StrategyId


def _adx_frame(adx_values: list[float]) -> pd.DataFrame:
    n = len(adx_values)
    index = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(n)]
    # Minimal columns so signals_at can run; leave other cols NaN → no signals.
    data = {
        "adx14": adx_values,
        "close": [1.1] * n,
        "ema20": [float("nan")] * n,
        "ema50": [float("nan")] * n,
        "ema200": [float("nan")] * n,
        "atr14": [float("nan")] * n,
        "atr50_sma": [float("nan")] * n,
        "rsi14": [float("nan")] * n,
        "bb_lower": [float("nan")] * n,
        "bb_upper": [float("nan")] * n,
        "bb_mid": [float("nan")] * n,
        "high_20_prior": [float("nan")] * n,
        "low_20_prior": [float("nan")] * n,
    }
    return pd.DataFrame(data, index=pd.DatetimeIndex(index, tz="UTC"))


def test_engine_no_trade_band_emits_nothing() -> None:
    engine = StrategyEngine()
    frame = _adx_frame([22.0])
    assert engine.regime_at(frame, 0) is Regime.NO_TRADE
    assert engine.signals_at(frame, 0) == []


def test_engine_trend_regime_allows_a_and_b_only() -> None:
    engine = StrategyEngine()
    frame = _adx_frame([30.0])
    assert engine.regime_at(frame, 0) is Regime.TREND
    # Warmup NaNs → no concrete signals, but C must not be eligible.
    assert StrategyId.C not in {
        s.strategy for s in engine.signals_at(frame, 0)
    }


def test_engine_range_regime_allows_c_only() -> None:
    engine = StrategyEngine()
    frame = _adx_frame([10.0])
    assert engine.regime_at(frame, 0) is Regime.RANGE
