"""MetaTrader5 adapter — Windows + installed ``MetaTrader5`` package only."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from autotrader.data.types import Candle, Timeframe

logger = logging.getLogger(__name__)

_TF_TO_MT5 = {
    Timeframe.H1: "TIMEFRAME_H1",
    Timeframe.H4: "TIMEFRAME_H4",
}


def mt5_package_available() -> bool:
    """True when the MetaTrader5 Python package can be imported (typically Windows)."""
    try:
        import MetaTrader5  # noqa: F401
    except ImportError:
        return False
    return True


class MT5MarketDataProvider:
    """
    Fetch closed candles from a running Exness MT5 terminal.

    Requires Windows, the ``MetaTrader5`` package, a logged-in terminal, and
    credentials from the local ``.env`` (never committed).
    """

    def __init__(
        self,
        *,
        login: int | str | None = None,
        password: str | None = None,
        server: str | None = None,
        path: str | None = None,
        symbols: list[str] | None = None,
        mt5_module: Any | None = None,
    ) -> None:
        self._login = int(login) if login not in (None, "") else None
        self._password = password or None
        self._server = server or None
        self._path = path or None
        self._symbols = [s.upper() for s in (symbols or ["EURUSD", "USDJPY"])]
        self._mt5 = mt5_module
        self._initialized = False

    def _module(self) -> Any:
        if self._mt5 is not None:
            return self._mt5
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError(
                "MetaTrader5 package is not installed. "
                "Install on Windows with: pip install MetaTrader5"
            ) from exc
        self._mt5 = mt5
        return mt5

    def connect(self) -> None:
        """Initialize the MT5 terminal connection (idempotent)."""
        if self._initialized:
            return
        mt5 = self._module()
        kwargs: dict[str, Any] = {}
        if self._path:
            kwargs["path"] = self._path
        if self._login is not None:
            kwargs["login"] = self._login
        if self._password is not None:
            kwargs["password"] = self._password
        if self._server is not None:
            kwargs["server"] = self._server
        ok = mt5.initialize(**kwargs) if kwargs else mt5.initialize()
        if not ok:
            code, message = mt5.last_error()
            raise RuntimeError(f"MT5 initialize failed: {code} {message}")
        self._initialized = True
        logger.info("MT5 connected (symbols=%s)", ",".join(self._symbols))

    def shutdown(self) -> None:
        if not self._initialized:
            return
        mt5 = self._module()
        mt5.shutdown()
        self._initialized = False

    def available_symbols(self) -> list[str]:
        return list(self._symbols)

    def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        count: int = 200,
    ) -> list[Candle]:
        if count < 1:
            raise ValueError("count must be >= 1")
        symbol = symbol.upper()
        if symbol not in self._symbols:
            raise KeyError(f"symbol not configured: {symbol}")

        self.connect()
        mt5 = self._module()
        tf_attr = _TF_TO_MT5[timeframe]
        mt5_tf = getattr(mt5, tf_attr)

        # Request one extra bar and drop the forming (last) bar if present.
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count + 1)
        if rates is None or len(rates) == 0:
            code, message = mt5.last_error()
            raise RuntimeError(f"MT5 copy_rates failed for {symbol} {timeframe}: {code} {message}")

        candles: list[Candle] = []
        for row in rates:
            # MT5 rate time is Unix seconds (broker/server); normalize to UTC.
            bar_time = datetime.fromtimestamp(int(row["time"]), tz=UTC)
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    time=bar_time,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["tick_volume"]),
                )
            )

        # Prefer excluding the in-progress bar: MT5 position 0 is the current bar.
        # copy_rates_from_pos(..., 0, n) returns oldest→newest ending at current.
        if len(candles) > count:
            candles = candles[:-1]
        return candles[-count:]
