import sqlite3
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from src.infrastructure.storage.database import open_database
from src.infrastructure.storage.orm import Base


def test_open_creates_schema(tmp_path: Path) -> None:
    engine = open_database(tmp_path / "cognia.sqlite3")

    tables = set(inspect(engine).get_table_names())
    with engine.connect() as db:
        revision = MigrationContext.configure(db).get_current_revision()
    engine.dispose()

    assert tables - {"alembic_version"} == set(Base.metadata.tables)
    assert len(Base.metadata.tables) == 25
    assert revision == "0001"


def test_open_twice_changes_nothing(tmp_path: Path) -> None:
    open_database(tmp_path / "cognia.sqlite3").dispose()
    engine = open_database(tmp_path / "cognia.sqlite3")

    with engine.connect() as db:
        settings = db.execute(text("SELECT count(*) FROM settings")).scalar()
        kinds = db.execute(text("SELECT count(*) FROM message_kinds")).scalar()
    engine.dispose()

    assert settings == 1
    assert kinds == 9


def test_ddl_rolls_back(tmp_path: Path) -> None:
    engine = open_database(tmp_path / "cognia.sqlite3")

    with pytest.raises(RuntimeError), engine.begin() as db:
        db.execute(text("CREATE TABLE half_done (id TEXT) STRICT"))
        raise RuntimeError

    assert "half_done" not in inspect(engine).get_table_names()
    engine.dispose()


def test_pragmas_apply(tmp_path: Path) -> None:
    engine = open_database(tmp_path / "cognia.sqlite3")

    with engine.connect() as db:
        values = {
            name: db.execute(text(f"PRAGMA {name}")).scalar()
            for name in ("journal_mode", "synchronous", "foreign_keys", "secure_delete")
        }
    engine.dispose()

    assert values == {
        "journal_mode": "wal",
        "synchronous": 2,
        "foreign_keys": 1,
        "secure_delete": 1,
    }


def test_old_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "cognia.sqlite3"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY)")
    old.execute("INSERT INTO conversations VALUES ('c1')")
    old.execute("PRAGMA user_version = 1")
    old.commit()
    old.close()

    with pytest.raises(OperationalError):
        open_database(path)

    old = sqlite3.connect(path)
    tables = old.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    assert [name for name, in tables] == ["conversations"]
    assert old.execute("SELECT id FROM conversations").fetchall() == [("c1",)]
    old.close()
