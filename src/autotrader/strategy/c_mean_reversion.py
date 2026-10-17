"""Strategy C — mean reversion (RSI + Bollinger)."""

from __future__ import annotations

import math

import pandas as pd

from autotrader.strategy.types import Side, Signal, StrategyId

STOP_ATR_MULT = 1.5
MAX_HOLD_BARS = 24
RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT = 70.0


def evaluate_mean_reversion(frame: pd.DataFrame, index: int) -> Signal | None:
    """
    ADX<20 (regime). Long: RSI<30 and close < lower BB(20,2).
    Short: RSI>70 and close > upper BB. Stop 1.5×ATR; exit mid-band or max 24 bars.
    """
    if index < 0 or index >= len(frame):
        return None

    row = frame.iloc[index]
    needed = ("rsi14", "bb_lower", "bb_upper", "bb_mid", "atr14", "close", "adx14")
    if any(math.isnan(float(row[c])) for c in needed):
        return None

    atr_v = float(row["atr14"])
    if atr_v <= 0:
        return None

    close = float(row["close"])
    rsi_v = float(row["rsi14"])
    bar_time = frame.index[index].to_pydatetime()

    if rsi_v < RSI_OVERSOLD and close < float(row["bb_lower"]):
        return Signal(
            strategy=StrategyId.C,
            side=Side.LONG,
            bar_index=index,
            bar_time=bar_time,
            entry_price=close,
            stop_price=close - STOP_ATR_MULT * atr_v,
            atr=atr_v,
            max_bars=MAX_HOLD_BARS,
            exit_mid_band=True,
            reason="C: RSI<30 and close below lower Bollinger",
        )

    if rsi_v > RSI_OVERBOUGHT and close > float(row["bb_upper"]):
        return Signal(
            strategy=StrategyId.C,
            side=Side.SHORT,
            bar_index=index,
            bar_time=bar_time,
            entry_price=close,
            stop_price=close + STOP_ATR_MULT * atr_v,
            atr=atr_v,
            max_bars=MAX_HOLD_BARS,
            exit_mid_band=True,
            reason="C: RSI>70 and close above upper Bollinger",
        )

    return None
