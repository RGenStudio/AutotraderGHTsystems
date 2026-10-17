"""Market data layer — candles via protocol (MT5 on Windows, mock on CI/Linux)."""

from autotrader.data.factory import create_market_data_provider
from autotrader.data.mock import MockMarketDataProvider
from autotrader.data.provider import MarketDataProvider
from autotrader.data.types import Candle, Timeframe

__all__ = [
    "Candle",
    "MarketDataProvider",
    "MockMarketDataProvider",
    "Timeframe",
    "create_market_data_provider",
]
