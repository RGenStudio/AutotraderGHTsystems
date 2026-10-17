"""M1 market data layer — mock backend, protocol, MT5 adapter (no real MT5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from autotrader.data.factory import create_market_data_provider
from autotrader.data.mock import MockMarketDataProvider, generate_fixture_candles
from autotrader.data.mt5 import MT5MarketDataProvider, mt5_package_available
from autotrader.data.provider import MarketDataProvider
from autotrader.data.types import Candle, Timeframe


def test_mock_provider_is_market_data_provider() -> None:
    provider = MockMarketDataProvider()
    assert isinstance(provider, MarketDataProvider)


def test_mock_fetches_h1_and_h4_for_both_symbols() -> None:
    provider = MockMarketDataProvider()
    assert provider.available_symbols() == ["EURUSD", "USDJPY"]
    for symbol in ("EURUSD", "USDJPY"):
        for tf in (Timeframe.H1, Timeframe.H4):
            bars = provider.fetch_candles(symbol, tf, count=50)
            assert len(bars) == 50
            assert bars[0].time < bars[-1].time
            assert all(b.symbol == symbol and b.timeframe == tf for b in bars)
            assert all(b.high >= b.low for b in bars)


def test_factory_defaults_to_mock_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MT5_LOGIN", raising=False)
    provider = create_market_data_provider(force_mock=True)
    assert isinstance(provider, MockMarketDataProvider)
    bars = provider.fetch_candles("EURUSD", Timeframe.H1, count=10)
    assert len(bars) == 10


def test_factory_without_credentials_uses_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MT5_LOGIN", raising=False)
    monkeypatch.delenv("MT5_PASSWORD", raising=False)
    provider = create_market_data_provider()
    assert isinstance(provider, MockMarketDataProvider)


def test_generate_fixture_deterministic() -> None:
    a = generate_fixture_candles("EURUSD", Timeframe.H1, count=20)
    b = generate_fixture_candles("EURUSD", Timeframe.H1, count=20)
    assert a == b


class _FakeRates(list):
    """List that also supports numpy-like structured access via dict rows."""


def test_mt5_adapter_with_fake_module() -> None:
    """Exercise MT5 adapter without the real MetaTrader5 package."""

    class FakeMT5:
        TIMEFRAME_H1 = 16385
        TIMEFRAME_H4 = 16388

        def __init__(self) -> None:
            self.initialized = False

        def initialize(self, **kwargs: Any) -> bool:
            self.initialized = True
            self.kwargs = kwargs
            return True

        def shutdown(self) -> None:
            self.initialized = False

        def last_error(self) -> tuple[int, str]:
            return (1, "ok")

        def copy_rates_from_pos(
            self, symbol: str, timeframe: int, start_pos: int, count: int
        ) -> list[dict[str, float | int]]:
            assert symbol == "EURUSD"
            assert timeframe == self.TIMEFRAME_H1
            # Include one extra "forming" bar at the end.
            base_ts = int(datetime(2024, 1, 8, 10, 0, tzinfo=UTC).timestamp())
            rows = []
            for i in range(count):
                rows.append(
                    {
                        "time": base_ts + i * 3600,
                        "open": 1.1 + i * 0.0001,
                        "high": 1.101 + i * 0.0001,
                        "low": 1.099 + i * 0.0001,
                        "close": 1.1005 + i * 0.0001,
                        "tick_volume": 10 + i,
                    }
                )
            return rows

    fake = FakeMT5()
    provider = MT5MarketDataProvider(
        login="12345",
        password="secret",
        server="Exness-MT5Trial",
        symbols=["EURUSD", "USDJPY"],
        mt5_module=fake,
    )
    bars = provider.fetch_candles("EURUSD", Timeframe.H1, count=5)
    assert len(bars) == 5
    assert all(isinstance(b, Candle) for b in bars)
    assert bars[0].time < bars[-1].time
    assert fake.initialized is True
    provider.shutdown()
    assert fake.initialized is False


def test_mt5_package_available_is_bool() -> None:
    assert isinstance(mt5_package_available(), bool)
