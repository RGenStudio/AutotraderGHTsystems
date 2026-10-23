"""SQLAlchemy engine helpers — SQLite WAL by default, Postgres when configured."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlalchemy.orm import Session, sessionmaker

from autotrader.config import REPO_ROOT, EnvSettings
from autotrader.db.models import Base

logger = logging.getLogger(__name__)

# Default on-disk path (repo-root relative). Overridden by DATABASE_URL / config.
DEFAULT_SQLITE_RELATIVE = Path("data") / "autotrader.db"

# Journal tables (must match models). Identifiers are a fixed whitelist.
JOURNAL_TABLES: tuple[str, ...] = (
    "signals",
    "decisions",
    "agent_calls",
    "orders",
    "trades",
    "costs",
    "system_events",
    "kill_switch_state",
)

_IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
_URL_SECRET = re.compile(r"(://[^:/@\s]+:)([^@/\s]+)@")
_PASSWORD_KV = re.compile(r"(?i)(password=)([^\s&]+)")
_POSTGRES_SCHEMES = frozenset(
    {
        "postgres",
        "postgresql",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }
)
_SSL_KEEP = frozenset({"require", "verify-ca", "verify-full"})
# Brief blips should retry sooner than the H1 bar interval.
DB_RETRY_SECONDS = 30.0


def default_sqlite_url(*, repo_root: Path | None = None) -> str:
    """Absolute ``sqlite:///…`` URL under ``data/autotrader.db``."""
    root = repo_root or REPO_ROOT
    db_path = (root / DEFAULT_SQLITE_RELATIVE).resolve()
    return f"sqlite:///{db_path}"


def is_postgres_url(url: str) -> bool:
    """True when ``url`` uses a Postgres scheme (any SQLAlchemy driver suffix)."""
    scheme = url.split(":", 1)[0].lower()
    return scheme in _POSTGRES_SCHEMES


def redact_database_url(url: str) -> str:
    """Hide userinfo passwords and ``password=`` fragments. Safe for logs."""
    redacted = _URL_SECRET.sub(r"\1***@", url)
    return _PASSWORD_KV.sub(r"\1***", redacted)


def safe_exception_text(exc: BaseException) -> str:
    """Exception summary with connection secrets removed."""
    return redact_database_url(f"{type(exc).__name__}: {exc}")[:500]


def is_database_connectivity_error(exc: BaseException) -> bool:
    """
    True for unreachable / dropped DB connections.

    Schema and constraint errors are not connectivity failures. Callers must
    not swap in SQLite when this is true and ``DATABASE_URL`` was set.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if _is_connectivity(current):
            return True
        nxt = current.__cause__
        if nxt is None:
            nxt = current.__context__
        current = nxt if isinstance(nxt, BaseException) else None
    return False


_NON_RETRYABLE_SQL = (
    "no such table",
    "syntax error",
    "unique constraint",
    "duplicate key",
    "not null",
    "foreign key",
)


def _is_connectivity(exc: BaseException) -> bool:
    """Classify one exception (not its cause chain)."""
    if isinstance(exc, OperationalError):
        message = str(exc).lower()
        if any(token in message for token in _NON_RETRYABLE_SQL):
            return False
        return True
    if isinstance(exc, (InterfaceError, DisconnectionError, SATimeoutError)):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    # Bare OSError covers "network unreachable". FileNotFoundError does not.
    if exc.__class__ is OSError:
        return True
    module = type(exc).__module__
    if "psycopg" in module and type(exc).__name__ in {
        "OperationalError",
        "InterfaceError",
        "ConnectionTimeout",
        "CannotConnectNow",
    }:
        return True
    return False


def resolve_database_url(
    *,
    override: str | None = None,
    env: EnvSettings | None = None,
    repo_root: Path | None = None,
) -> str:
    """
    Resolve DB URL: explicit override → ``DATABASE_URL`` env → default SQLite file.

    Empty / whitespace ``DATABASE_URL`` is ignored (falls back to the SQLite file).
    A non-empty Postgres URL is rewritten to the psycopg v3 driver with
    ``sslmode=require``. It is never replaced with SQLite.
    """
    if override is not None and override.strip():
        return normalize_database_url(override.strip())
    settings = env or EnvSettings()
    if settings.database_url is not None and settings.database_url.strip():
        return normalize_database_url(settings.database_url.strip())
    # Optional YAML key via env AUTOTRADER_DATABASE_URL already covered by Settings;
    # also allow bare file path from config if callers pass it as override.
    _ = os.environ.get("AUTOTRADER_DATABASE_URL")  # reserved; EnvSettings uses DATABASE_URL
    return default_sqlite_url(repo_root=repo_root)


def normalize_database_url(url: str) -> str:
    """
    Keep SQLite URLs unchanged.

    Postgres URLs become ``postgresql+psycopg://`` and require SSL
    (``require`` / ``verify-ca`` / ``verify-full``). Weaker ``sslmode`` values
    are upgraded to ``require``.
    """
    if not is_postgres_url(url):
        return url
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme in {"postgres", "postgresql", "postgresql+psycopg2"}:
        scheme = "postgresql+psycopg"
    elif scheme != "postgresql+psycopg":
        scheme = "postgresql+psycopg"
    query: dict[str, str] = {}
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        query[key] = value
    if query.get("sslmode", "").lower() not in _SSL_KEEP:
        query["sslmode"] = "require"
    path = parts.path or "/postgres"
    return urlunsplit((scheme, parts.netloc, path, urlencode(query), parts.fragment))


def _ensure_sqlite_parent(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    # sqlite:///:memory: and sqlite:///file
    raw = url.removeprefix("sqlite:///")
    if raw in {":memory:", ""} or raw.startswith("file:"):
        return
    path = Path(raw)
    if path.parent and str(path.parent) not in {".", ""}:
        path.parent.mkdir(parents=True, exist_ok=True)


def _enable_sqlite_wal(dbapi_conn: object, _connection_record: object) -> None:
    cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _postgres_statement_timeout(dbapi_conn: object, _connection_record: object) -> None:
    """Bound a stuck query so the H1 loop can reach the next retry."""
    cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
    cursor.execute("SET statement_timeout = '30s'")
    cursor.close()


def _postgres_port(url: str) -> int | None:
    try:
        return urlsplit(url).port
    except ValueError:
        return None


def create_db_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """
    Create an engine.

    SQLite file URLs enable WAL + foreign keys on connect.
    Postgres uses psycopg v3, ``sslmode=require``, pool pre-ping, and disables
    prepared statements so a transaction-pooler URI (port 6543) does not crash.
    The long-running engine should still use the session pooler (port 5432).
    """
    resolved = resolve_database_url(override=url)
    _ensure_sqlite_parent(resolved)
    connect_args: dict[str, object] = {}
    kwargs: dict[str, object] = {"echo": echo, "future": True}
    if resolved.startswith("sqlite:"):
        # Needed for WAL + multi-thread test access with same engine
        connect_args["check_same_thread"] = False
        kwargs["connect_args"] = connect_args
        engine = create_engine(resolved, **kwargs)  # type: ignore[arg-type]
        event.listen(engine, "connect", _enable_sqlite_wal)
        # Apply WAL immediately on first connection
        with engine.connect() as conn:
            mode = conn.execute(text("PRAGMA journal_mode")).scalar()
            _ = mode  # typically 'wal' for file DBs; memory may stay 'memory'
        return engine

    if is_postgres_url(resolved):
        # psycopg3: None disables auto-prepared statements (Supabase txn pooler).
        connect_args["prepare_threshold"] = None
        connect_args["connect_timeout"] = 10
        kwargs["connect_args"] = connect_args
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 1800
        port = _postgres_port(resolved)
        if port == 6543:
            logger.warning(
                "DATABASE_URL uses port 6543 (Supabase transaction pooler). "
                "The long-running engine should use the session pooler on port 5432. "
                "Prepared statements are disabled so this URL can still connect."
            )
        engine = create_engine(resolved, **kwargs)  # type: ignore[arg-type]
        event.listen(engine, "connect", _postgres_statement_timeout)
        return engine

    # Any other explicit URL (not empty — empty already became SQLite).
    # Do not rewrite it to SQLite; a mis-set DATABASE_URL must surface.
    return create_engine(resolved, echo=echo, future=True)


def _is_postgresql_engine(engine: Engine) -> bool:
    name = getattr(getattr(engine, "dialect", None), "name", None)
    return (name == "postgresql") is True


def _quote_table(name: str) -> str:
    if not _IDENT.fullmatch(name):
        raise ValueError(f"refusing non-identifier table name: {name!r}")
    return name


def journal_rls_statements() -> str:
    """Postgres DO block: enable RLS, revoke anon, grant service_role. No policies."""
    tables = [_quote_table(name) for name in JOURNAL_TABLES]
    lines = ["DO $$", "BEGIN"]
    for table in tables:
        lines.append(f"  ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;")
    for role in ("anon", "authenticated"):
        lines.append(f"  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN")
        for table in tables:
            lines.append(f"    REVOKE ALL ON TABLE public.{table} FROM {role};")
        lines.append("  END IF;")
    lines.append("  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN")
    for table in tables:
        lines.append(f"    GRANT SELECT ON TABLE public.{table} TO service_role;")
    lines.append("  END IF;")
    lines.append("END $$;")
    return "\n".join(lines)


def enable_journal_rls(engine: Engine) -> None:
    """
    Enable RLS and revoke anon/authenticated on Postgres.

    No policies are created, so the anon API key cannot read the journal.
    The engine and the dashboard connect as the database owner / service role,
    which bypasses RLS. SQLite is unchanged. Failures are logged by ``init_db``
    unless they are connectivity errors (those propagate).
    """
    if not _is_postgresql_engine(engine):
        return
    statement = journal_rls_statements()
    with engine.begin() as conn:
        conn.execute(text(statement))
    logger.info("Postgres journal RLS enabled (no anon policies)")


def init_db(engine: Engine | None = None, *, url: str | None = None) -> Engine:
    """Create all tables if missing; enable Postgres RLS; return the engine used."""
    eng = engine or create_db_engine(url)
    Base.metadata.create_all(eng)
    try:
        enable_journal_rls(eng)
    except Exception as exc:
        if is_database_connectivity_error(exc):
            raise
        logger.warning(
            "Could not enable journal RLS (%s). Tables were created. "
            "Anon access stays blocked only after RLS succeeds.",
            safe_exception_text(exc),
        )
    return eng


def make_session_factory(engine: Engine) -> Callable[[], Session]:
    """Return a no-arg session factory bound to ``engine``."""
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory
