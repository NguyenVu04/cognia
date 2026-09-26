"""The one SQLite file, opened the way every store needs it.

One connection, used only from the thread that opened it — the GUI thread.
SQLAlchemy's default for a file is a pool with SQLite's same-thread check
switched off, which would let the reply worker quietly open a second connection;
``StaticPool`` with the check on keeps ADR 0002's promise that touching the
store from the wrong thread fails loudly.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.pool import StaticPool

from src.infrastructure.storage.migrate import migrate

_PRAGMAS = (
    # WAL survives an abrupt shutdown; FULL means a committed row is on the
    # platter before we say it was recorded. NFR-08 asks for both.
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA foreign_keys=ON",
    # Deleted rows are overwritten, not left in free pages: a removed memory
    # item is gone from the disk (NFR-04, UC-13, UC-14).
    "PRAGMA secure_delete=ON",
)


def open_database(path: Path) -> Engine:
    """Open (or create) the file, and bring it up to the newest schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite", database=str(path)),
        poolclass=StaticPool,
        connect_args={"check_same_thread": True},
    )
    event.listen(engine, "connect", _configure)

    connection = engine.raw_connection()
    try:
        migrate(connection.driver_connection)
    finally:
        connection.close()
    return engine


def _configure(dbapi_connection, _record) -> None:
    for pragma in _PRAGMAS:
        dbapi_connection.execute(pragma)
