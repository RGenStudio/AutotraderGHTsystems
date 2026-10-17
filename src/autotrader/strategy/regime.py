"""ADX regime selection — pure code gate before strategy A/B/C."""

from __future__ import annotations

from autotrader.strategy.types import Regime, StrategyId

ADX_TREND_THRESHOLD = 25.0
ADX_RANGE_THRESHOLD = 20.0


def classify_regime(adx_value: float) -> Regime:
    """
    Brief rule:
    - ADX > 25 → trend (A or B)
    - ADX < 20 → range (C)
    - ADX 20–25 → no trade
    """
    if adx_value > ADX_TREND_THRESHOLD:
        return Regime.TREND
    if adx_value < ADX_RANGE_THRESHOLD:
        return Regime.RANGE
    return Regime.NO_TRADE


def strategies_for_regime(regime: Regime) -> tuple[StrategyId, ...]:
    if regime is Regime.TREND:
        return (StrategyId.A, StrategyId.B)
    if regime is Regime.RANGE:
        return (StrategyId.C,)
    return ()
