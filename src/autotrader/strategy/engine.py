"""Strategy Engine — code-only candidate entries (AI does not create signals)."""

from __future__ import annotations

import math

import pandas as pd

from autotrader.data.types import Candle
from autotrader.strategy.a_trend import evaluate_trend
from autotrader.strategy.b_breakout import evaluate_breakout
from autotrader.strategy.c_mean_reversion import evaluate_mean_reversion
from autotrader.strategy.features import build_feature_frame
from autotrader.strategy.regime import classify_regime, strategies_for_regime
from autotrader.strategy.types import Regime, Signal, StrategyId


class StrategyEngine:
    """
    Evaluates strategies A/B/C on closed bars only.

    Signals are candidate entries for later AI filter / Risk Engine — this layer
    never invents discretionary AI entries.
    """

    def __init__(
        self,
        *,
        enabled: tuple[StrategyId, ...] | None = None,
    ) -> None:
        self.enabled = enabled or (StrategyId.A, StrategyId.B, StrategyId.C)

    def features(self, candles: list[Candle]) -> pd.DataFrame:
        return build_feature_frame(candles)

    def regime_at(self, frame: pd.DataFrame, index: int) -> Regime:
        if index < 0 or index >= len(frame):
            return Regime.NO_TRADE
        adx_v = frame.iloc[index]["adx14"]
        if math.isnan(float(adx_v)):
            return Regime.NO_TRADE
        return classify_regime(float(adx_v))

    def signals_at(self, frame: pd.DataFrame, index: int) -> list[Signal]:
        """Candidate signals for one closed bar (may be empty)."""
        regime = self.regime_at(frame, index)
        allowed = set(strategies_for_regime(regime)) & set(self.enabled)
        out: list[Signal] = []
        if StrategyId.A in allowed:
            sig = evaluate_trend(frame, index)
            if sig is not None:
                out.append(sig)
        if StrategyId.B in allowed:
            sig = evaluate_breakout(frame, index)
            if sig is not None:
                out.append(sig)
        if StrategyId.C in allowed:
            sig = evaluate_mean_reversion(frame, index)
            if sig is not None:
                out.append(sig)
        return out

    def scan(self, candles: list[Candle]) -> list[Signal]:
        """Scan full closed-bar series; each signal uses only data ≤ that bar."""
        frame = self.features(candles)
        signals: list[Signal] = []
        for i in range(len(frame)):
            signals.extend(self.signals_at(frame, i))
        return signals
