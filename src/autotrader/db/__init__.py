"""SQLite (WAL) by default; Postgres/Supabase when ``DATABASE_URL`` is set."""

from __future__ import annotations

from autotrader.db.engine import (
    DB_RETRY_SECONDS,
    DEFAULT_SQLITE_RELATIVE,
    JOURNAL_TABLES,
    create_db_engine,
    enable_journal_rls,
    init_db,
    is_database_connectivity_error,
    is_postgres_url,
    make_session_factory,
    normalize_database_url,
    redact_database_url,
    resolve_database_url,
    safe_exception_text,
)
from autotrader.db.models import (
    AgentCallRow,
    Base,
    CostRow,
    DecisionRow,
    KillSwitchStateRow,
    OrderRow,
    SignalRow,
    SystemEventRow,
    TradeRow,
)

__all__ = [
    "AgentCallRow",
    "Base",
    "CostRow",
    "DB_RETRY_SECONDS",
    "DEFAULT_SQLITE_RELATIVE",
    "DecisionRow",
    "JOURNAL_TABLES",
    "KillSwitchStateRow",
    "OrderRow",
    "SignalRow",
    "SystemEventRow",
    "TradeRow",
    "create_db_engine",
    "enable_journal_rls",
    "init_db",
    "is_database_connectivity_error",
    "is_postgres_url",
    "make_session_factory",
    "normalize_database_url",
    "redact_database_url",
    "resolve_database_url",
    "safe_exception_text",
]
