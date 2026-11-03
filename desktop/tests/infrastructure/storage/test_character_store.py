import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.domain.character.models import CHOSEN, RESTORED, Version
from src.domain.emotion.models import Pad, Temperament
from src.domain.ports import CharacterStoreFailed
from src.infrastructure.storage.character_store import SqliteCharacterStore

MONDAY = datetime(2026, 11, 2, 8, 0, 0, 125000, tzinfo=timezone.utc)
TUESDAY = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)

V1 = Version(
    id="a" * 32,
    number=1,
    template_id="yuna",
    name="Yuna",
    role="The Gentle Companion",
    description="You are Yuna.\n\nFor example: ...",
    appearance_id="yuna",
    temperament=Temperament(0.4, 30.0, 720.0, Pad(0.10, -0.05, 0.00)),
    origin=CHOSEN,
    created_at=MONDAY,
)
V2 = replace(
    V1,
    id="b" * 32,
    number=2,
    template_id="rin",
    name="Rin",
    temperament=Temperament(0.4, 30.0, 480.0, Pad(0.00, 0.05, 0.25)),
    created_at=TUESDAY,
)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "cognia.sqlite3"


@pytest.fixture
def store(path: Path):
    store = SqliteCharacterStore(path)
    yield store
    store.close()


def test_current_none_on_new_file(store: SqliteCharacterStore) -> None:
    assert store.current() is None


def test_add_puts_version_in_force(store: SqliteCharacterStore) -> None:
    store.add(V1)

    assert store.current() == V1


def test_add_sets_settings_pointer(store: SqliteCharacterStore, path: Path) -> None:
    store.add(V1)

    db = sqlite3.connect(path)
    assert db.execute("SELECT character_version_id FROM settings").fetchall() == [
        (V1.id,)
    ]
    db.close()


def test_versions_newest_first(store: SqliteCharacterStore) -> None:
    store.add(V1)
    store.add(V2)

    assert [v.number for v in store.versions()] == [2, 1]
    assert store.current() == V2


def test_round_trip_all_fields(store: SqliteCharacterStore) -> None:
    restored = replace(V1, id="c" * 32, number=3, origin=RESTORED, created_at=TUESDAY)
    store.add(V1)
    store.add(V2)
    store.add(restored)

    assert store.versions() == [restored, V2, V1]


def test_duplicate_number_fails_cleanly(store: SqliteCharacterStore) -> None:
    store.add(V1)

    with pytest.raises(CharacterStoreFailed):
        store.add(replace(V2, number=1))

    assert store.current() == V1
    assert store.versions() == [V1]


def test_unreadable_history(store: SqliteCharacterStore, path: Path) -> None:
    store.add(V1)
    db = sqlite3.connect(path)
    db.execute("ALTER TABLE character_versions RENAME TO lost")
    db.commit()
    db.close()

    with pytest.raises(CharacterStoreFailed):
        store.versions()
