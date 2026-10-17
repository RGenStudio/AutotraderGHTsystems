"""Bollinger Bands indicator."""

from __future__ import annotations

import pandas as pd

from autotrader.indicators import bollinger_bands


def test_bollinger_mid_is_sma() -> None:
    close = pd.Series([float(i) for i in range(1, 31)])
    bb = bollinger_bands(close, period=20, num_std=2.0)
    assert bb["mid"].iloc[-1] == close.iloc[-20:].mean()
    assert bb["upper"].iloc[-1] > bb["mid"].iloc[-1]
    assert bb["lower"].iloc[-1] < bb["mid"].iloc[-1]
