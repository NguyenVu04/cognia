import sqlite3
from pathlib import Path

import pytest

from src.infrastructure.storage.app_usage_store import SqliteAppUsage
from src.infrastructure.storage.database import Database


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "cognia.sqlite3"


@pytest.fixture
def usage(path: Path):
    db = Database.open(path)
    yield SqliteAppUsage(db)
    db.close()


def rows(path: Path) -> list[tuple]:
    connection = sqlite3.connect(path)
    found = connection.execute(
        "SELECT day, hour, app_name, minutes FROM app_usage ORDER BY app_name"
    ).fetchall()
    connection.close()
    return found


def test_put_keeps_minutes_per_app(usage, path: Path) -> None:
    usage.put("2026-11-06", 9, {"code.exe": 40, "firefox.exe": 12, "": 5, "x.exe": 0})

    assert rows(path) == [
        ("2026-11-06", 9, "code.exe", 40),
        ("2026-11-06", 9, "firefox.exe", 12),
    ]


def test_put_again_replaces_the_hour(usage, path: Path) -> None:
    usage.put("2026-11-06", 9, {"code.exe": 40})
    usage.put("2026-11-06", 9, {"code.exe": 45})

    assert rows(path) == [("2026-11-06", 9, "code.exe", 45)]
