"""Bring the database file up to the newest schema.

``migrations/NNNN_*.sql`` are applied in order, each exactly once. SQLite's own
``PRAGMA user_version`` records how many have run, so there is no bookkeeping
table in the user's file. A migration and its version bump commit together or
not at all; a failure leaves the file as it was.

No Alembic (ADR 0003): the schema is small, SQLite is the only target, and a
numbered SQL file is readable by anyone who can read the database itself.

Run this module to check the migrations against ``schema.py``::

    uv run python -m src.infrastructure.storage.migrate
"""

from __future__ import annotations

import sqlite3
from importlib.resources import files
from importlib.resources.abc import Traversable


def scripts() -> list[Traversable]:
    """Every migration, in the order it must run."""
    folder = files(__package__).joinpath("migrations")
    return sorted(
        (item for item in folder.iterdir() if item.name.endswith(".sql")),
        key=lambda item: item.name,
    )


def migrate(db: sqlite3.Connection) -> None:
    """Apply every migration the file has not seen yet."""
    version = db.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(scripts()[version:], start=version + 1):
        # A renumbered or missing file would otherwise skip a migration silently.
        if int(script.name[:4]) != number:
            raise RuntimeError(f"expected migration {number:04}, found {script.name}")
        try:
            db.executescript(
                f"BEGIN;\n{script.read_text('utf-8')}\n"
                f"PRAGMA user_version = {number};\nCOMMIT;"
            )
        except sqlite3.Error:
            db.rollback()
            raise


# ── self-check ────────────────────────────────────────────────────────────

# The two tables as the stdlib store created them, before migrations existed.
_BEFORE_MIGRATIONS = """
CREATE TABLE conversations (
    id TEXT PRIMARY KEY, character_id TEXT NOT NULL, title TEXT NOT NULL,
    started_at TEXT NOT NULL, last_active_at TEXT NOT NULL
);
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('u', 'c')), text TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
"""


def _self_check() -> None:
    import tempfile
    import warnings
    from datetime import datetime, timezone
    from pathlib import Path

    from sqlalchemy import URL, MetaData, create_engine
    from sqlalchemy.exc import SAWarning

    from src.infrastructure.storage import schema

    naive = "2026-01-15T10:00:00.123456"
    expected = datetime.fromisoformat(naive).astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    )

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "check.sqlite3"
        db = sqlite3.connect(path)
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(_BEFORE_MIGRATIONS)
        db.execute("INSERT INTO conversations VALUES ('c1', 'wren', 't', ?, ?)", (naive, naive))
        db.execute("INSERT INTO messages VALUES ('m1', 'c1', 'u', 'hi', '', ?)", (naive,))
        db.commit()

        # An existing file upgrades, keeping its rows, with times now in UTC.
        migrate(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == len(scripts())
        assert db.execute("SELECT started_at FROM conversations").fetchone()[0] == expected
        assert db.execute("SELECT created_at FROM messages").fetchone()[0] == expected

        # Running again changes nothing.
        migrate(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == len(scripts())
        assert db.execute("SELECT count(*) FROM settings").fetchone()[0] == 1

        # Rules the schema itself enforces.
        db.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', ?)", (expected,))
        try:
            db.execute("INSERT INTO sessions (id, started_at) VALUES ('s2', ?)", (expected,))
            raise AssertionError("a second open session was accepted")
        except sqlite3.IntegrityError:
            pass
        try:
            db.execute(
                "INSERT INTO memory_items VALUES ('n1', 'noticed', 'x', NULL, NULL, ?, ?)",
                (expected, expected),
            )
            raise AssertionError("a noticed item without evidence was accepted")
        except sqlite3.IntegrityError:
            pass
        db.rollback()
        db.close()

        # schema.py mirrors what the migrations actually built.
        engine = create_engine(URL.create("sqlite", database=str(path)))
        built = MetaData()
        with warnings.catch_warnings():
            # The one-open-session index is an expression; reflection skips it.
            warnings.simplefilter("ignore", SAWarning)
            built.reflect(engine)
        engine.dispose()

        def shape(metadata: MetaData) -> dict[str, dict[str, tuple]]:
            return {
                table.name: {
                    column.name: (
                        str(column.type),
                        column.primary_key,
                        # SQLite lets a TEXT primary key be NULL; compare the rest.
                        None if column.primary_key else column.nullable,
                    )
                    for column in table.columns
                }
                for table in metadata.tables.values()
            }

        actual, mirrored = shape(built), shape(schema.metadata)
        if actual != mirrored:
            for name in sorted(actual.keys() | mirrored.keys()):
                if actual.get(name) != mirrored.get(name):
                    print(f"{name}:\n  migrations {actual.get(name)}\n  schema.py  {mirrored.get(name)}")
            raise AssertionError("schema.py does not match the migrations")

    print(f"ok: {len(scripts())} migration(s), {len(actual)} tables match schema.py")


if __name__ == "__main__":
    _self_check()
