"""
Indicator implementations aligned with common MetaTrader5 defaults.

Uses Wilder's smoothing (RMA) for RSI, ATR, and ADX — the same family MT5 uses
for ``iRSI``, ``iATR``, and ``iADX``. EMA uses standard exponential MA
(``EMA = close * k + prev * (1-k)``, ``k = 2/(period+1)``).
"""

from __future__ import annotations

import pandas as pd

from autotrader.data.types import Candle


def candles_to_frame(candles: list[Candle]) -> pd.DataFrame:
    """Convert candles (oldest→newest) to an OHLCV DataFrame indexed by UTC time."""
    if not candles:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    rows = [
        {
            "time": c.time,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
    ]
    frame = pd.DataFrame(rows).set_index("time").sort_index()
    return frame


def wilder_rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's Moving Average (RMA) — used by MT5 RSI/ATR/ADX."""
    if period < 1:
        raise ValueError("period must be >= 1")
    return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (``span=period``, ``adjust=False``)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    return close.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder / MT5-style)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = wilder_rma(gain, period)
    avg_loss = wilder_rma(loss, period)
    rs = avg_gain / avg_loss
    result = 100.0 - (100.0 / (1.0 + rs))
    zero_loss = avg_loss == 0
    result = result.mask(zero_loss & (avg_gain > 0), 100.0)
    result = result.mask(zero_loss & (avg_gain == 0), 50.0)
    return result.astype(float)


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range (Wilder / MT5-style)."""
    return wilder_rma(true_range(high, low, close), period)


def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """
    Bollinger Bands (SMA mid ± ``num_std`` * rolling std).

    Returns columns: ``mid``, ``upper``, ``lower``.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if num_std < 0:
        raise ValueError("num_std must be >= 0")
    mid = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    return pd.DataFrame(
        {
            "mid": mid,
            "upper": mid + num_std * std,
            "lower": mid - num_std * std,
        }
    )


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.DataFrame:
    """
    Average Directional Index (Wilder / MT5-style).

    Returns a DataFrame with columns: ``adx``, ``plus_di``, ``minus_di``.
    """
    if period < 1:
        raise ValueError("period must be >= 1")

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr = true_range(high, low, close)
    atr_v = wilder_rma(tr, period)
    plus_di = 100.0 * wilder_rma(plus_dm, period) / atr_v
    minus_di = 100.0 * wilder_rma(minus_dm, period) / atr_v

    di_sum = plus_di + minus_di
    dx = (100.0 * (plus_di - minus_di).abs() / di_sum.replace(0.0, pd.NA)).fillna(0.0)
    adx_v = wilder_rma(dx, period)

    return pd.DataFrame(
        {
            "adx": adx_v,
            "plus_di": plus_di,
            "minus_di": minus_di,
        }
    )
