"""ADX regime gate unit tests."""

from autotrader.strategy.regime import classify_regime, strategies_for_regime
from autotrader.strategy.types import Regime, StrategyId


def test_regime_trend_above_25() -> None:
    assert classify_regime(25.01) is Regime.TREND
    assert classify_regime(40.0) is Regime.TREND
    assert strategies_for_regime(Regime.TREND) == (StrategyId.A, StrategyId.B)


def test_regime_range_below_20() -> None:
    assert classify_regime(19.99) is Regime.RANGE
    assert classify_regime(5.0) is Regime.RANGE
    assert strategies_for_regime(Regime.RANGE) == (StrategyId.C,)


def test_regime_no_trade_band() -> None:
    assert classify_regime(20.0) is Regime.NO_TRADE
    assert classify_regime(25.0) is Regime.NO_TRADE
    assert classify_regime(22.5) is Regime.NO_TRADE
    assert strategies_for_regime(Regime.NO_TRADE) == ()
