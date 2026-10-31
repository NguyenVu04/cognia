"""The one SQLite file, opened the way every store needs it.

One connection, used only from the thread that opened it — the GUI thread.
SQLAlchemy's default for a file is a pool with SQLite's same-thread check
switched off, which would let the reply worker quietly open a second connection;
``StaticPool`` with the check on keeps ADR 0002's promise that touching the
store from the wrong thread fails loudly.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Connection, Engine, create_engine, event
from sqlalchemy.pool import StaticPool

_MIGRATIONS = Path(__file__).parent / "migrations"

_PRAGMAS = (
    # WAL survives an abrupt shutdown; FULL means a committed row is on the
    # platter before we say it was recorded. NFR-07 asks for both.
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA foreign_keys=ON",
    # Deleted rows are overwritten, not left in free pages: a removed memory
    # item is gone from the disk (NFR-03, UC-13, UC-14).
    "PRAGMA secure_delete=ON",
)


def open_database(path: Path) -> Engine:
    """Open (or create) the file, and bring it up to the newest schema.

    A file from before the Alembic baseline raises ``OperationalError`` and
    stays as it was (ADR 0003).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite", database=str(path)),
        poolclass=StaticPool,
        connect_args={"check_same_thread": True},
    )
    event.listen(engine, "connect", _configure)
    event.listen(engine, "begin", _begin)
    _upgrade(engine)
    return engine


def _upgrade(engine: Engine) -> None:
    """Apply every revision in one transaction, so a failure leaves the file alone."""
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS).replace("%", "%%"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def _configure(dbapi_connection, _record) -> None:
    # Left alone, sqlite3 opens no transaction for DDL, and a failed revision
    # would leave half a schema. _begin opens every transaction instead.
    dbapi_connection.isolation_level = None
    for pragma in _PRAGMAS:
        dbapi_connection.execute(pragma)


def _begin(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN")
