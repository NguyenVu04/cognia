import sqlite3
from pathlib import Path

import pytest

from src.infrastructure.storage.database import Database
from src.infrastructure.storage.settings_store import SqliteSettings

GPU = "NVIDIA GeForce RTX 3050 Ti Laptop GPU"


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "cognia.sqlite3"


@pytest.fixture
def settings(path: Path):
    db = Database.open(path)
    yield SqliteSettings(db)
    db.close()


def test_no_device_on_new_file(settings: SqliteSettings) -> None:
    assert settings.chat_device() is None


def test_device_round_trip(settings: SqliteSettings) -> None:
    settings.set_chat_device(GPU)

    assert settings.chat_device() == GPU


def test_device_replaced(settings: SqliteSettings) -> None:
    settings.set_chat_device("Intel(R) Iris(R) Xe Graphics")
    settings.set_chat_device(GPU)

    assert settings.chat_device() == GPU


def test_unreadable_gives_none(settings: SqliteSettings, path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE settings DROP COLUMN chat_device")
    connection.commit()
    connection.close()

    assert settings.chat_device() is None
    settings.set_chat_device(GPU)  # does not raise
