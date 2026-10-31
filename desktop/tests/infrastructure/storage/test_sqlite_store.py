import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.domain.conversation.models import COMPANION, USER, Message
from src.infrastructure.storage.sqlite_store import SqliteConversationStore

START = datetime(2026, 10, 31, 12, 0)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "cognia.sqlite3"


@pytest.fixture
def store(path: Path):
    store = SqliteConversationStore(path)
    yield store
    store.close()


def test_latest_returns_created(store: SqliteConversationStore) -> None:
    created = store.create(START)

    assert store.latest().id == created.id


def test_role_is_stored_in_full(store: SqliteConversationStore, path: Path) -> None:
    conversation = store.create(START)
    store.append(Message.new(conversation.id, USER, "hi", START))

    db = sqlite3.connect(path)
    assert db.execute("SELECT role FROM messages").fetchall() == [("user",)]
    db.close()


def test_role_reads_back(store: SqliteConversationStore) -> None:
    conversation = store.create(START)
    store.append(Message.new(conversation.id, COMPANION, "hello", START))

    assert store.history(conversation.id)[0].role == COMPANION


def test_note_is_not_stored(store: SqliteConversationStore) -> None:
    conversation = store.create(START)
    store.append(Message.new(conversation.id, COMPANION, "hello", START, note="x"))

    assert store.history(conversation.id)[0].note == ""


def test_append_lifts_conversation(store: SqliteConversationStore) -> None:
    conversation = store.create(START)
    later = datetime(2026, 10, 31, 13, 0)
    store.append(Message.new(conversation.id, USER, "hi", later))

    assert store.latest().last_active_at == later.astimezone(timezone.utc)


def test_history_limit_keeps_last(store: SqliteConversationStore) -> None:
    conversation = store.create(START)
    for number in range(3):
        store.append(Message.new(conversation.id, USER, str(number), START))

    last = store.history(conversation.id, limit=2)

    assert [message.text for message in last] == ["1", "2"]


def test_delete_removes_messages(store: SqliteConversationStore) -> None:
    conversation = store.create(START)
    store.append(Message.new(conversation.id, USER, "hi", START))

    store.delete(conversation.id)

    assert store.history(conversation.id) == []
    assert store.latest() is None
