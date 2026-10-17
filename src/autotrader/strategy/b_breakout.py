"""Strategy B — volatility breakout."""

from __future__ import annotations

import math

import pandas as pd

from autotrader.strategy.types import Side, Signal, StrategyId

STOP_ATR_MULT = 1.5
TP_R_MULT = 2.0
TRAIL_ATR_MULT = 1.5


def evaluate_breakout(frame: pd.DataFrame, index: int) -> Signal | None:
    """
    ADX>25 and ATR>50-bar ATR average (regime + volatility filter).
    Long: close above prior 20-bar high; Short: below prior 20-bar low.
    Stop 1.5×ATR; TP 2R or trailing 1.5×ATR.
    """
    if index < 1 or index >= len(frame):
        return None

    row = frame.iloc[index]
    needed = ("atr14", "atr50_sma", "close", "high_20_prior", "low_20_prior", "adx14")
    if any(math.isnan(float(row[c])) for c in needed):
        return None

    atr_v = float(row["atr14"])
    atr_avg = float(row["atr50_sma"])
    if atr_v <= 0 or atr_v <= atr_avg:
        return None

    close = float(row["close"])
    prior_high = float(row["high_20_prior"])
    prior_low = float(row["low_20_prior"])
    bar_time = frame.index[index].to_pydatetime()

    if close > prior_high:
        stop = close - STOP_ATR_MULT * atr_v
        risk = close - stop
        return Signal(
            strategy=StrategyId.B,
            side=Side.LONG,
            bar_index=index,
            bar_time=bar_time,
            entry_price=close,
            stop_price=stop,
            atr=atr_v,
            take_profit=close + TP_R_MULT * risk,
            trail_atr_mult=TRAIL_ATR_MULT,
            reason="B: close above prior 20-bar high with ATR>50-bar avg",
        )

    if close < prior_low:
        stop = close + STOP_ATR_MULT * atr_v
        risk = stop - close
        return Signal(
            strategy=StrategyId.B,
            side=Side.SHORT,
            bar_index=index,
            bar_time=bar_time,
            entry_price=close,
            stop_price=stop,
            atr=atr_v,
            take_profit=close - TP_R_MULT * risk,
            trail_atr_mult=TRAIL_ATR_MULT,
            reason="B: close below prior 20-bar low with ATR>50-bar avg",
        )

    return None
