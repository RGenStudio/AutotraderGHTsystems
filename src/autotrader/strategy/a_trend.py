"""Strategy A — trend following (EMA200 filter + EMA20/50 cross)."""

from __future__ import annotations

import math

import pandas as pd

from autotrader.strategy.types import Side, Signal, StrategyId

STOP_ATR_MULT = 2.0
TRAIL_ATR_MULT = 2.5


def evaluate_trend(frame: pd.DataFrame, index: int) -> Signal | None:
    """
    Long: close > EMA200 and EMA20 crosses above EMA50.
    Short: close < EMA200 and EMA20 crosses below EMA50.
    Requires ADX>25 (enforced by regime gate in the engine).
    Stop 2×ATR; exit on EMA reverse or trailing 2.5×ATR (managed by backtester).
    """
    if index < 1 or index >= len(frame):
        return None

    row = frame.iloc[index]
    prev = frame.iloc[index - 1]
    needed = ("ema20", "ema50", "ema200", "atr14", "close", "adx14")
    if any(math.isnan(float(row[c])) for c in needed):
        return None
    if math.isnan(float(prev["ema20"])) or math.isnan(float(prev["ema50"])):
        return None

    close = float(row["close"])
    atr_v = float(row["atr14"])
    if atr_v <= 0:
        return None

    ema20, ema50, ema200 = float(row["ema20"]), float(row["ema50"]), float(row["ema200"])
    prev_ema20, prev_ema50 = float(prev["ema20"]), float(prev["ema50"])
    bar_time = frame.index[index].to_pydatetime()

    crossed_up = prev_ema20 <= prev_ema50 and ema20 > ema50
    crossed_down = prev_ema20 >= prev_ema50 and ema20 < ema50

    if close > ema200 and crossed_up:
        stop = close - STOP_ATR_MULT * atr_v
        return Signal(
            strategy=StrategyId.A,
            side=Side.LONG,
            bar_index=index,
            bar_time=bar_time,
            entry_price=close,
            stop_price=stop,
            atr=atr_v,
            trail_atr_mult=TRAIL_ATR_MULT,
            reason="A: close>EMA200 and EMA20 crossed above EMA50",
        )

    if close < ema200 and crossed_down:
        stop = close + STOP_ATR_MULT * atr_v
        return Signal(
            strategy=StrategyId.A,
            side=Side.SHORT,
            bar_index=index,
            bar_time=bar_time,
            entry_price=close,
            stop_price=stop,
            atr=atr_v,
            trail_atr_mult=TRAIL_ATR_MULT,
            reason="A: close<EMA200 and EMA20 crossed below EMA50",
        )

    return None


def ema_reverse_exit(frame: pd.DataFrame, index: int, side: Side) -> bool:
    """True when EMA20/50 cross reverses against the open side on this closed bar."""
    if index < 1:
        return False
    row = frame.iloc[index]
    prev = frame.iloc[index - 1]
    vals = (row["ema20"], row["ema50"], prev["ema20"], prev["ema50"])
    if any(math.isnan(float(x)) for x in vals):
        return False
    ema20, ema50 = float(row["ema20"]), float(row["ema50"])
    prev_ema20, prev_ema50 = float(prev["ema20"]), float(prev["ema50"])
    if side is Side.LONG:
        return prev_ema20 >= prev_ema50 and ema20 < ema50
    return prev_ema20 <= prev_ema50 and ema20 > ema50
