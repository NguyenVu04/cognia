import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from src.domain.character.models import CHOSEN, Version
from src.domain.emotion.models import Pad, Temperament
from src.domain.events.models import EventKind
from src.domain.ports import CharacterStoreFailed
from src.infrastructure.storage.character_store import SqliteCharacterStore
from src.infrastructure.storage.database import Database, open_database
from src.infrastructure.storage.event_log import SqliteEventLog
from src.infrastructure.storage.orm import Base

MONDAY = datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)
V1 = Version(
    id="a" * 32,
    number=1,
    template_id="yuna",
    name="Yuna",
    role="The Gentle Companion",
    description="You are Yuna.",
    appearance_id="yuna",
    temperament=Temperament(0.4, 30.0, 720.0, Pad(0.10, 0.0, 0.0)),
    origin=CHOSEN,
    created_at=MONDAY,
)


@pytest.fixture
def db(tmp_path: Path):
    db = Database.open(tmp_path / "cognia.sqlite3")
    yield db
    db.close()


def _chosen(log: SqliteEventLog) -> None:
    log.append(MONDAY, 0, EventKind.CHARACTER_CHANGED, {"version_id": V1.id}, None)


def _count(db: Database, table: str) -> int:
    with db.transaction() as connection:
        return connection.execute(text(f"SELECT count(*) FROM {table}")).scalar()


def test_open_creates_schema(tmp_path: Path) -> None:
    engine = open_database(tmp_path / "cognia.sqlite3")

    tables = set(inspect(engine).get_table_names())
    with engine.connect() as db:
        revision = MigrationContext.configure(db).get_current_revision()
    engine.dispose()

    assert tables - {"alembic_version"} == set(Base.metadata.tables)
    assert len(Base.metadata.tables) == 21
    assert revision == "0003"


def test_open_twice_changes_nothing(tmp_path: Path) -> None:
    open_database(tmp_path / "cognia.sqlite3").dispose()
    engine = open_database(tmp_path / "cognia.sqlite3")

    with engine.connect() as db:
        settings = db.execute(text("SELECT count(*) FROM settings")).scalar()
        kinds = db.execute(text("SELECT count(*) FROM message_kinds")).scalar()
    engine.dispose()

    assert settings == 1
    assert kinds == 7


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


def test_transaction_commits_all(db: Database) -> None:
    log, store = SqliteEventLog(db), SqliteCharacterStore(db)

    with db.transaction():
        _chosen(log)
        store.add(V1)

    assert _count(db, "events") == 1
    assert store.current() == V1


def test_transaction_rolls_back_all(db: Database) -> None:
    log, store = SqliteEventLog(db), SqliteCharacterStore(db)
    store.add(V1)

    with pytest.raises(CharacterStoreFailed), db.transaction():
        _chosen(log)
        store.add(V1)

    assert _count(db, "events") == 0
    assert store.versions() == [V1]


def test_nested_transaction_joins(db: Database) -> None:
    log = SqliteEventLog(db)

    with pytest.raises(RuntimeError), db.transaction():
        with db.transaction():
            _chosen(log)
        raise RuntimeError

    assert _count(db, "events") == 0


def test_call_outside_transaction_commits(db: Database, tmp_path: Path) -> None:
    _chosen(SqliteEventLog(db))

    other = sqlite3.connect(tmp_path / "cognia.sqlite3")
    assert other.execute("SELECT count(*) FROM events").fetchone() == (1,)
    other.close()
