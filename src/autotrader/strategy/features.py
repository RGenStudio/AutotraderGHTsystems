"""Indicator feature frame used by strategies (closed-bar only)."""

from __future__ import annotations

import pandas as pd

from autotrader.data.types import Candle
from autotrader.indicators import adx, atr, bollinger_bands, candles_to_frame, ema, rsi


def build_feature_frame(candles: list[Candle]) -> pd.DataFrame:
    """
    Compute all indicators needed by strategies A/B/C on closed OHLC.

    Index aligns with candle order (oldest→newest). Warmup rows may be NaN.
    """
    frame = candles_to_frame(candles)
    if frame.empty:
        return frame

    frame["ema20"] = ema(frame["close"], 20)
    frame["ema50"] = ema(frame["close"], 50)
    frame["ema200"] = ema(frame["close"], 200)
    frame["rsi14"] = rsi(frame["close"], 14)
    frame["atr14"] = atr(frame["high"], frame["low"], frame["close"], 14)
    frame["atr50_sma"] = frame["atr14"].rolling(window=50, min_periods=50).mean()
    adx_df = adx(frame["high"], frame["low"], frame["close"], 14)
    frame["adx14"] = adx_df["adx"]
    bb = bollinger_bands(frame["close"], period=20, num_std=2.0)
    frame["bb_mid"] = bb["mid"]
    frame["bb_upper"] = bb["upper"]
    frame["bb_lower"] = bb["lower"]
    # Prior 20-bar high/low excluding current bar (no look-ahead into current range).
    frame["high_20_prior"] = frame["high"].shift(1).rolling(window=20, min_periods=20).max()
    frame["low_20_prior"] = frame["low"].shift(1).rolling(window=20, min_periods=20).min()
    return frame
