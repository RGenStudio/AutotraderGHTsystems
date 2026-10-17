"""SQLAlchemy engine helpers — SQLite WAL by default."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from autotrader.config import REPO_ROOT, EnvSettings
from autotrader.db.models import Base

# Default on-disk path (repo-root relative). Overridden by DATABASE_URL / config.
DEFAULT_SQLITE_RELATIVE = Path("data") / "autotrader.db"


def default_sqlite_url(*, repo_root: Path | None = None) -> str:
    """Absolute ``sqlite:///…`` URL under ``data/autotrader.db``."""
    root = repo_root or REPO_ROOT
    db_path = (root / DEFAULT_SQLITE_RELATIVE).resolve()
    return f"sqlite:///{db_path}"


def resolve_database_url(
    *,
    override: str | None = None,
    env: EnvSettings | None = None,
    repo_root: Path | None = None,
) -> str:
    """
    Resolve DB URL: explicit override → ``DATABASE_URL`` env → default SQLite file.

    Empty / whitespace ``DATABASE_URL`` is ignored (falls back to default file).
    """
    if override is not None and override.strip():
        return override.strip()
    settings = env or EnvSettings()
    if settings.database_url is not None and settings.database_url.strip():
        return settings.database_url.strip()
    # Optional YAML key via env AUTOTRADER_DATABASE_URL already covered by Settings;
    # also allow bare file path from config if callers pass it as override.
    _ = os.environ.get("AUTOTRADER_DATABASE_URL")  # reserved; EnvSettings uses DATABASE_URL
    return default_sqlite_url(repo_root=repo_root)


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


def create_db_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """
    Create an engine. For SQLite file URLs, enable WAL + foreign keys on connect.
    """
    resolved = resolve_database_url(override=url)
    _ensure_sqlite_parent(resolved)
    connect_args: dict[str, object] = {}
    if resolved.startswith("sqlite:"):
        # Needed for WAL + multi-thread test access with same engine
        connect_args["check_same_thread"] = False
    engine = create_engine(resolved, echo=echo, future=True, connect_args=connect_args)
    if resolved.startswith("sqlite:"):
        event.listen(engine, "connect", _enable_sqlite_wal)
        # Apply WAL immediately on first connection
        with engine.connect() as conn:
            mode = conn.execute(text("PRAGMA journal_mode")).scalar()
            _ = mode  # typically 'wal' for file DBs; memory may stay 'memory'
    return engine


def init_db(engine: Engine | None = None, *, url: str | None = None) -> Engine:
    """Create all tables if missing; return the engine used."""
    eng = engine or create_db_engine(url)
    Base.metadata.create_all(eng)
    return eng


def make_session_factory(engine: Engine) -> Callable[[], Session]:
    """Return a no-arg session factory bound to ``engine``."""
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory
