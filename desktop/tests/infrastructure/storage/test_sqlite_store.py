from datetime import datetime
from pathlib import Path

from src.infrastructure.storage.sqlite_store import SqliteConversationStore


def test_latest_returns_created(tmp_path: Path) -> None:
    store = SqliteConversationStore(tmp_path / "cognia.sqlite3")
    created = store.create("c1", datetime(2026, 10, 31, 12, 0))

    assert store.latest().id == created.id
    store.close()
