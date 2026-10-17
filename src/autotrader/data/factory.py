"""Select MT5 backend on Windows with package+creds, else mock/fixture."""

from __future__ import annotations

import logging
import sys

from autotrader.config import EnvSettings, load_config
from autotrader.data.mock import MockMarketDataProvider
from autotrader.data.mt5 import MT5MarketDataProvider, mt5_package_available
from autotrader.data.provider import MarketDataProvider

logger = logging.getLogger(__name__)


def create_market_data_provider(
    *,
    env: EnvSettings | None = None,
    force_mock: bool = False,
) -> MarketDataProvider:
    """
    Build a :class:`MarketDataProvider`.

    - Prefer real MT5 when on Windows, package importable, and ``MT5_LOGIN`` set.
    - Otherwise return :class:`MockMarketDataProvider` (Linux CI / no credentials).
    """
    if force_mock:
        return MockMarketDataProvider()

    settings = env or EnvSettings()
    cfg = load_config()
    symbols = list(cfg.symbols)

    on_windows = sys.platform.startswith("win")
    has_login = bool(settings.mt5_login)
    if (
        not force_mock
        and on_windows
        and mt5_package_available()
        and has_login
    ):
        logger.info("Using MetaTrader5 market data backend")
        return MT5MarketDataProvider(
            login=settings.mt5_login,
            password=settings.mt5_password,
            server=settings.mt5_server,
            path=settings.mt5_path,
            symbols=symbols,
        )

    reason = []
    if force_mock:
        reason.append("force_mock")
    if not on_windows:
        reason.append(f"platform={sys.platform}")
    if not mt5_package_available():
        reason.append("MetaTrader5 package missing")
    if not has_login:
        reason.append("MT5_LOGIN unset")
    logger.info("Using mock market data backend (%s)", ", ".join(reason) or "default")
    return MockMarketDataProvider(symbols=symbols)
