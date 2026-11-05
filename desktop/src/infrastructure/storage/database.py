"""The one SQLite file, opened the way every store needs it.

One connection, used only from the thread that opened it — the GUI thread.
SQLAlchemy's default for a file is a pool with SQLite's same-thread check
switched off, which would let the reply worker quietly open a second connection;
``StaticPool`` with the check on makes touching the store from the wrong
thread fail loudly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Connection, Engine, create_engine, event
from sqlalchemy.pool import StaticPool

_MIGRATIONS = Path(__file__).parent / "migrations"

_PRAGMAS = (
    # WAL survives an abrupt shutdown; FULL means a committed row is on the
    # platter before we say it was recorded. An abrupt shutdown loses nothing.
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA foreign_keys=ON",
    # Deleted rows are overwritten, not left in free pages: a removed memory
    # item is gone from the disk.
    "PRAGMA secure_delete=ON",
)


def open_database(path: Path) -> Engine:
    """Open (or create) the file, and bring it up to the newest schema.

    A file from before the Alembic baseline raises ``OperationalError`` and
    stays as it was.
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


class Database:
    """The one file and its one connection, shared by every store.

    Every store call inside :meth:`transaction` is part of that transaction:
    all of it commits, or none of it. A store call outside one runs in its own.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._open: Connection | None = None

    @classmethod
    def open(cls, path: Path) -> Database:
        """Open the file as :func:`open_database` does, with the same errors."""
        return cls(open_database(path))

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """A connection in a transaction. Inside another transaction this joins
        it, and only the outer one commits."""
        if self._open is not None:
            yield self._open
            return
        with self._engine.begin() as connection:
            self._open = connection
            try:
                yield connection
            finally:
                self._open = None

    def compact(self) -> None:
        """Rewrite the file and empty the write-ahead log.

        The log can still hold copies of pages that held deleted rows, and the
        file keeps free pages, so after an erasure both are rewritten. Runs
        outside any transaction. Raises ``sqlite3.Error`` if SQLite refuses.
        """
        if self._open is not None:
            raise RuntimeError("compact() cannot run inside a transaction")
        connection = self._engine.raw_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            cursor.execute("VACUUM")
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            cursor.close()
        finally:
            connection.close()

    def close(self) -> None:
        self._engine.dispose()


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
