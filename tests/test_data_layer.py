"""M1 market data layer — mock backend, protocol, MT5 adapter (no real MT5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from autotrader.data.factory import create_market_data_provider
from autotrader.data.mock import MockMarketDataProvider, generate_fixture_candles
from autotrader.data.mt5 import (
    MT5MarketDataProvider,
    matching_broker_symbols,
    mt5_package_available,
    normalize_mt5_path,
)
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


def _fake_rate_rows(count: int) -> list[dict[str, float | int]]:
    base_ts = int(datetime(2024, 1, 8, 10, 0, tzinfo=UTC).timestamp())
    rows: list[dict[str, float | int]] = []
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


class _SymbolInfo:
    def __init__(self, name: str) -> None:
        self.name = name


def test_mt5_adapter_with_fake_module() -> None:
    """Exercise MT5 adapter without the real MetaTrader5 package."""

    class FakeMT5:
        TIMEFRAME_H1 = 16385
        TIMEFRAME_H4 = 16388

        def __init__(self) -> None:
            self.initialized = False
            self.selected: list[tuple[str, bool]] = []
            self.copy_calls = 0

        def initialize(self, **kwargs: Any) -> bool:
            self.initialized = True
            self.kwargs = kwargs
            return True

        def shutdown(self) -> None:
            self.initialized = False

        def last_error(self) -> tuple[int, str]:
            return (1, "ok")

        def symbol_select(self, symbol: str, enable: bool) -> bool:
            self.selected.append((symbol, enable))
            return True

        def symbols_get(self) -> list[_SymbolInfo]:
            return [_SymbolInfo("EURUSD"), _SymbolInfo("USDJPY")]

        def copy_rates_from_pos(
            self, symbol: str, timeframe: int, start_pos: int, count: int
        ) -> list[dict[str, float | int]]:
            self.copy_calls += 1
            assert symbol == "EURUSD"
            assert timeframe == self.TIMEFRAME_H1
            return _fake_rate_rows(count)

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
    assert fake.selected == [("EURUSD", True)]
    assert fake.copy_calls == 1
    provider.shutdown()
    assert fake.initialized is False


def test_mt5_symbol_map_uses_broker_wire_name() -> None:
    class FakeMT5:
        TIMEFRAME_H1 = 16385
        TIMEFRAME_H4 = 16388

        def __init__(self) -> None:
            self.selected: list[str] = []
            self.copy_symbols: list[str] = []

        def initialize(self, **kwargs: Any) -> bool:
            return True

        def last_error(self) -> tuple[int, str]:
            return (1, "ok")

        def symbol_select(self, symbol: str, enable: bool) -> bool:
            self.selected.append(symbol)
            return True

        def symbols_get(self) -> list[_SymbolInfo]:
            return [_SymbolInfo("EURUSDm"), _SymbolInfo("USDJPYm")]

        def copy_rates_from_pos(
            self, symbol: str, timeframe: int, start_pos: int, count: int
        ) -> list[dict[str, float | int]]:
            self.copy_symbols.append(symbol)
            assert symbol == "EURUSDm"
            return _fake_rate_rows(count)

        def shutdown(self) -> None:
            return None

    fake = FakeMT5()
    provider = MT5MarketDataProvider(
        symbols=["EURUSD", "USDJPY"],
        symbol_map={"EURUSD": "EURUSDm", "USDJPY": "USDJPYm"},
        mt5_module=fake,
    )
    bars = provider.fetch_candles("EURUSD", Timeframe.H1, count=3)
    assert len(bars) == 3
    assert all(b.symbol == "EURUSD" for b in bars)
    assert fake.selected == ["EURUSDm"]
    assert fake.copy_symbols == ["EURUSDm"]


def test_mt5_preserves_broker_native_symbol_casing() -> None:
    """Config ``EURUSDm`` must be sent to MT5 as-is (not uppercased to EURUSDM)."""

    class FakeMT5:
        TIMEFRAME_H1 = 16385
        TIMEFRAME_H4 = 16388

        def __init__(self) -> None:
            self.copy_symbols: list[str] = []

        def initialize(self, **kwargs: Any) -> bool:
            return True

        def last_error(self) -> tuple[int, str]:
            return (1, "ok")

        def symbol_select(self, symbol: str, enable: bool) -> bool:
            return True

        def symbols_get(self) -> list[_SymbolInfo]:
            return [_SymbolInfo("EURUSDm")]

        def copy_rates_from_pos(
            self, symbol: str, timeframe: int, start_pos: int, count: int
        ) -> list[dict[str, float | int]]:
            self.copy_symbols.append(symbol)
            return _fake_rate_rows(count)

        def shutdown(self) -> None:
            return None

    fake = FakeMT5()
    provider = MT5MarketDataProvider(symbols=["EURUSDm"], mt5_module=fake)
    assert provider.available_symbols() == ["EURUSDM"]
    bars = provider.fetch_candles("EURUSDm", Timeframe.H1, count=2)
    assert len(bars) == 2
    assert bars[0].symbol == "EURUSDM"
    assert fake.copy_symbols == ["EURUSDm"]


def test_mt5_copy_rates_retries_after_symbol_select() -> None:
    class FakeMT5:
        TIMEFRAME_H1 = 16385
        TIMEFRAME_H4 = 16388

        def __init__(self) -> None:
            self.copy_calls = 0
            self.select_calls = 0
            self._error = (1, "Success")

        def initialize(self, **kwargs: Any) -> bool:
            return True

        def last_error(self) -> tuple[int, str]:
            return self._error

        def symbol_select(self, symbol: str, enable: bool) -> bool:
            self.select_calls += 1
            return True

        def symbols_get(self) -> list[_SymbolInfo]:
            return [_SymbolInfo("EURUSD")]

        def copy_rates_from_pos(
            self, symbol: str, timeframe: int, start_pos: int, count: int
        ) -> list[dict[str, float | int]] | None:
            self.copy_calls += 1
            if self.copy_calls == 1:
                self._error = (-1, "Call failed")
                return None
            self._error = (1, "Success")
            return _fake_rate_rows(count)

        def shutdown(self) -> None:
            return None

    fake = FakeMT5()
    provider = MT5MarketDataProvider(symbols=["EURUSD"], mt5_module=fake)
    bars = provider.fetch_candles("EURUSD", Timeframe.H1, count=4)
    assert len(bars) == 4
    assert fake.copy_calls == 2
    assert fake.select_calls == 2


def test_mt5_copy_rates_failure_lists_matching_symbols() -> None:
    class FakeMT5:
        TIMEFRAME_H1 = 16385
        TIMEFRAME_H4 = 16388

        def initialize(self, **kwargs: Any) -> bool:
            return True

        def last_error(self) -> tuple[int, str]:
            return (-1, "Call failed")

        def symbol_select(self, symbol: str, enable: bool) -> bool:
            return True

        def symbols_get(self) -> list[_SymbolInfo]:
            return [
                _SymbolInfo("EURUSDm"),
                _SymbolInfo("EURUSD.a"),
                _SymbolInfo("USDJPYm"),
                _SymbolInfo("XAUUSD"),
            ]

        def copy_rates_from_pos(
            self, symbol: str, timeframe: int, start_pos: int, count: int
        ) -> None:
            return None

        def shutdown(self) -> None:
            return None

    provider = MT5MarketDataProvider(symbols=["EURUSD"], mt5_module=FakeMT5())
    with pytest.raises(RuntimeError) as excinfo:
        provider.fetch_candles("EURUSD", Timeframe.H1, count=5)
    msg = str(excinfo.value)
    assert "copy_rates failed" in msg
    assert "Login/initialize can succeed while rates fail" in msg
    assert "EURUSDm" in msg
    assert "EURUSD.a" in msg
    assert "XAUUSD" not in msg


def test_matching_broker_symbols_filters_by_needle() -> None:
    class FakeMT5:
        def symbols_get(self) -> list[_SymbolInfo]:
            return [
                _SymbolInfo("EURUSDm"),
                _SymbolInfo("EURUSD"),
                _SymbolInfo("USDJPY"),
            ]

    assert matching_broker_symbols(FakeMT5(), "eurusd") == ["EURUSDm", "EURUSD"]


def test_mt5_package_available_is_bool() -> None:
    assert isinstance(mt5_package_available(), bool)


def test_normalize_mt5_path_fixes_tab_footgun() -> None:
    """Unquoted ``\\t`` in .env turns ``...5\\terminal`` into ``...5erminal``."""
    broken = r"C:\Program Files\MetaTrader 5erminal64.exe"
    fixed = normalize_mt5_path(broken)
    assert fixed is not None
    assert fixed.endswith("5/terminal64.exe")
    assert "5erminal" not in fixed


def test_normalize_mt5_path_fixes_literal_tab() -> None:
    broken = "C:/MetaTrader 5\terminal64.exe"  # real tab between 5 and erminal
    fixed = normalize_mt5_path(broken)
    assert fixed is not None
    assert "\t" not in fixed
    assert fixed.endswith("5/terminal64.exe")


def test_normalize_mt5_path_leaves_good_paths() -> None:
    good = "C:/Program Files/MetaTrader 5/terminal64.exe"
    assert normalize_mt5_path(good) == good
    assert normalize_mt5_path(None) is None
    assert normalize_mt5_path("   ") is None


def test_mt5_connect_uses_normalized_path() -> None:
    class FakeMT5:
        TIMEFRAME_H1 = 16385
        TIMEFRAME_H4 = 16388

        def initialize(self, **kwargs: Any) -> bool:
            self.kwargs = kwargs
            return True

        def last_error(self) -> tuple[int, str]:
            return (1, "ok")

        def shutdown(self) -> None:
            return None

    fake = FakeMT5()
    provider = MT5MarketDataProvider(
        path=r"D:\Exness\MetaTrader 5erminal64.exe",
        mt5_module=fake,
    )
    provider.connect()
    assert fake.kwargs["path"].endswith("5/terminal64.exe")
    assert "5erminal" not in fake.kwargs["path"]
