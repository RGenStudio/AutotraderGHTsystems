"""MetaTrader5 adapter — Windows + installed ``MetaTrader5`` package only."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autotrader.data.types import Candle, Timeframe

logger = logging.getLogger(__name__)

_TF_TO_MT5 = {
    Timeframe.H1: "TIMEFRAME_H1",
    Timeframe.H4: "TIMEFRAME_H4",
}

# ``MT5_PATH=...\MetaTrader 5\terminal64.exe`` — unquoted ``\t`` becomes a tab
# (or is dropped), leaving ``...5erminal64.exe`` / ``...5<TAB>erminal64.exe``.
_BROKEN_TERMINAL64 = re.compile(r"(?i)5[\t]?erminal64\.exe$")


def normalize_mt5_path(path: str | None) -> str | None:
    """
    Expand and repair common ``MT5_PATH`` mis-parses from ``.env``.

    Prefer forward slashes in ``.env`` (e.g. ``C:/Program Files/.../terminal64.exe``)
    so parsers never treat ``\\t`` as a tab escape.
    """
    if path is None:
        return None
    raw = path.strip()
    if not raw:
        return None
    fixed = raw
    if _BROKEN_TERMINAL64.search(fixed):
        # Forward slash avoids a second ``\t`` escape if the value is re-parsed.
        repaired = _BROKEN_TERMINAL64.sub("5/terminal64.exe", fixed)
        logger.warning(
            "MT5_PATH looks mis-parsed (missing backslash before terminal64); "
            "corrected %r → %r. Prefer forward slashes in .env, e.g. "
            "MT5_PATH=C:/Path/To/terminal64.exe",
            raw,
            repaired,
        )
        fixed = repaired
    return str(Path(fixed).expanduser())


def mt5_package_available() -> bool:
    """True when the MetaTrader5 Python package can be imported (typically Windows)."""
    try:
        import MetaTrader5  # noqa: F401
    except ImportError:
        return False
    return True


def _symbol_info_name(info: Any) -> str | None:
    """Extract a symbol name from ``symbols_get`` / ``symbol_info`` results."""
    if info is None:
        return None
    if isinstance(info, str):
        return info
    name = getattr(info, "name", None)
    if isinstance(name, str) and name:
        return name
    if isinstance(info, dict):
        raw = info.get("name")
        return raw if isinstance(raw, str) else None
    return None


def matching_broker_symbols(mt5: Any, needle: str, *, limit: int = 25) -> list[str]:
    """
    Return visible MT5 symbol names that contain ``needle`` (case-insensitive).

    Used in error messages when ``copy_rates`` fails (e.g. Exness ``EURUSDm``).
    """
    needle_u = needle.strip().upper()
    if not needle_u:
        return []
    try:
        all_symbols = mt5.symbols_get()
    except Exception:  # noqa: BLE001 — best-effort diagnostics only
        logger.debug("symbols_get failed while building error hint", exc_info=True)
        return []
    if not all_symbols:
        return []
    matches: list[str] = []
    seen: set[str] = set()
    for info in all_symbols:
        name = _symbol_info_name(info)
        if not name:
            continue
        if needle_u in name.upper() and name not in seen:
            seen.add(name)
            matches.append(name)
            if len(matches) >= limit:
                break
    return matches


class MT5MarketDataProvider:
    """
    Fetch closed candles from a running Exness MT5 terminal.

    Requires Windows, the ``MetaTrader5`` package, a logged-in terminal, and
    credentials from the local ``.env`` (never committed).

    **Login vs rates:** ``connect()`` / ``initialize`` succeeding only means the
    terminal accepted credentials. ``copy_rates_from_pos`` can still fail with
    ``(-1, 'Call failed')`` when the symbol is missing from Market Watch, uses a
    broker suffix (Exness ``EURUSDm``), or is otherwise not selectable. Those are
    distinct failures — do not treat a green login as proof that rates work.
    """

    def __init__(
        self,
        *,
        login: int | str | None = None,
        password: str | None = None,
        server: str | None = None,
        path: str | None = None,
        symbols: list[str] | None = None,
        symbol_map: dict[str, str] | None = None,
        mt5_module: Any | None = None,
    ) -> None:
        self._login = int(login) if login not in (None, "") else None
        self._password = password or None
        self._server = server or None
        self._path = normalize_mt5_path(path)
        raw_symbols = [s.strip() for s in (symbols or ["EURUSD", "USDJPY"]) if s.strip()]
        if not raw_symbols:
            raw_symbols = ["EURUSD", "USDJPY"]
        # App-facing identity stays uppercase; wire names preserve broker casing
        # (Exness ``EURUSDm``) via ``symbol_map`` or the original config spelling.
        self._symbols = [s.upper() for s in raw_symbols]
        self._wire_names: dict[str, str] = {}
        mapped = {
            str(k).strip().upper(): str(v).strip()
            for k, v in (symbol_map or {}).items()
            if str(k).strip() and str(v).strip()
        }
        for orig in raw_symbols:
            key = orig.upper()
            self._wire_names[key] = mapped.get(key, orig)
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

    def _wire_symbol(self, symbol: str) -> str:
        """Broker-facing name for MT5 API calls (may differ from app symbol)."""
        return self._wire_names.get(symbol.upper(), symbol)

    def connect(self) -> None:
        """Initialize the MT5 terminal connection (idempotent)."""
        if self._initialized:
            return
        mt5 = self._module()
        kwargs: dict[str, Any] = {}
        # Re-normalize in case path was set after construction (tests / hot reload).
        path = normalize_mt5_path(self._path)
        self._path = path
        if path:
            kwargs["path"] = path
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
        wire = ",".join(f"{s}->{self._wire_names[s]}" for s in self._symbols)
        logger.info("MT5 connected (symbols=%s)", wire)

    def shutdown(self) -> None:
        if not self._initialized:
            return
        mt5 = self._module()
        mt5.shutdown()
        self._initialized = False

    def available_symbols(self) -> list[str]:
        return list(self._symbols)

    def _clear_last_error(self, mt5: Any) -> tuple[int, str] | None:
        """
        Read ``last_error`` so a later failure is not confused with a stale code.

        The MetaTrader5 package has no explicit clear API; reading is the usual
        way to snapshot/discard the previous status before a retry.
        """
        try:
            result = mt5.last_error()
        except Exception:  # noqa: BLE001 — diagnostics only
            return None
        if isinstance(result, tuple) and len(result) >= 2:
            return int(result[0]), str(result[1])
        return None

    def _ensure_symbol_selected(self, mt5: Any, wire_symbol: str) -> bool:
        """Add ``wire_symbol`` to Market Watch; required before ``copy_rates`` on many brokers."""
        try:
            ok = mt5.symbol_select(wire_symbol, True)
        except Exception as exc:  # noqa: BLE001 — surface as rates failure later
            logger.warning("MT5 symbol_select(%r) raised: %s", wire_symbol, exc)
            return False
        if not ok:
            code_msg = self._clear_last_error(mt5)
            logger.warning(
                "MT5 symbol_select(%r) returned False (last_error=%s)",
                wire_symbol,
                code_msg,
            )
        return bool(ok)

    def _copy_rates_error_message(
        self,
        mt5: Any,
        *,
        app_symbol: str,
        wire_symbol: str,
        timeframe: Timeframe,
        code: Any,
        message: Any,
    ) -> str:
        """Build a actionable error when rates fail after a successful login."""
        needles = [wire_symbol, app_symbol]
        # Strip a trailing single-letter suffix (e.g. EURUSDm → EURUSD) for hints.
        for base in (wire_symbol, app_symbol):
            if len(base) > 6 and base[:6].isalpha():
                needles.append(base[:6])
        seen: set[str] = set()
        matches: list[str] = []
        for needle in needles:
            key = needle.upper()
            if key in seen:
                continue
            seen.add(key)
            for name in matching_broker_symbols(mt5, needle):
                if name not in matches:
                    matches.append(name)

        hint_parts = [
            f"MT5 copy_rates failed for {app_symbol} (wire={wire_symbol}) {timeframe}: "
            f"{code} {message}.",
            "Login/initialize can succeed while rates fail — often the symbol is not "
            "in Market Watch or the broker uses a suffix (Exness: EURUSDm / USDJPYm).",
            "Fix: set config symbols to Market Watch names, or use symbol_map "
            "(e.g. EURUSD: EURUSDm), and ensure symbol_select succeeds.",
        ]
        if matches:
            shown = ", ".join(matches[:25])
            hint_parts.append(f"Visible/matching symbols: {shown}.")
        else:
            hint_parts.append(
                "No matching symbols from symbols_get — check Market Watch / symbol name."
            )
        return " ".join(hint_parts)

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

        wire_symbol = self._wire_symbol(symbol)
        self.connect()
        mt5 = self._module()
        tf_attr = _TF_TO_MT5[timeframe]
        mt5_tf = getattr(mt5, tf_attr)

        # Market Watch select + clear stale last_error before the first rates call.
        self._ensure_symbol_selected(mt5, wire_symbol)
        self._clear_last_error(mt5)

        # Request one extra bar and drop the forming (last) bar if present.
        rates = mt5.copy_rates_from_pos(wire_symbol, mt5_tf, 0, count + 1)
        if rates is None or len(rates) == 0:
            # Retry once: re-select, clear error, copy again (common Exness footgun).
            logger.warning(
                "MT5 copy_rates empty/None for %s (wire=%s); re-selecting and retrying once",
                symbol,
                wire_symbol,
            )
            self._ensure_symbol_selected(mt5, wire_symbol)
            self._clear_last_error(mt5)
            rates = mt5.copy_rates_from_pos(wire_symbol, mt5_tf, 0, count + 1)

        if rates is None or len(rates) == 0:
            code, message = mt5.last_error()
            raise RuntimeError(
                self._copy_rates_error_message(
                    mt5,
                    app_symbol=symbol,
                    wire_symbol=wire_symbol,
                    timeframe=timeframe,
                    code=code,
                    message=message,
                )
            )

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
