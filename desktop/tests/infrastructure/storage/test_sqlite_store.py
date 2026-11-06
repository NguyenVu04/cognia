import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.domain.conversation.models import COMPANION, USER, Message
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.sqlite_store import SqliteConversationStore

START = datetime(2026, 10, 31, 12, 0)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "cognia.sqlite3"


@pytest.fixture
def store(path: Path):
    db = Database.open(path)
    yield SqliteConversationStore(db)
    db.close()


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


def test_delete_failure_raises(store, monkeypatch) -> None:
    from sqlalchemy.exc import OperationalError

    from src.domain.ports import ConversationStoreFailed
    from src.infrastructure.storage.sqlite_store import NOT_DELETED

    conversation = store.create(START)

    def broken():
        raise OperationalError("DELETE", {}, Exception("disk I/O error"))

    monkeypatch.setattr(store._db, "transaction", broken)
    with pytest.raises(ConversationStoreFailed, match=NOT_DELETED):
        store.delete(conversation.id)


def test_summary_round_trip(store) -> None:
    from src.domain.conversation.models import Summary

    conversation = store.create(START)

    assert store.summary(conversation.id) is None
    assert store.set_summary(conversation.id, Summary("They met.", 4))
    assert store.summary(conversation.id) == Summary("They met.", 4)


def test_set_summary_older_refused(store) -> None:
    from src.domain.conversation.models import Summary

    conversation = store.create(START)
    store.set_summary(conversation.id, Summary("Newer.", 6))

    assert not store.set_summary(conversation.id, Summary("Older.", 4))
    assert store.summary(conversation.id) == Summary("Newer.", 6)


def test_set_summary_missing_conversation(store) -> None:
    from src.domain.conversation.models import Summary

    assert not store.set_summary("gone", Summary("They met.", 4))


def test_summary_deleted_with_conversation(store, path) -> None:
    from src.domain.conversation.models import Summary

    conversation = store.create(START)
    store.set_summary(conversation.id, Summary("They met.", 4))
    store.delete(conversation.id)

    connection = sqlite3.connect(path)
    found = connection.execute(
        "SELECT count(*) FROM conversations WHERE summary IS NOT NULL"
    ).fetchone()
    connection.close()
    assert found == (0,)


# ── search ───────────────────────────────────────────────────────────────


def said(store, conversation, *texts):
    from datetime import timedelta

    return [
        store.append(
            Message.new(conversation.id, USER, text_, START + timedelta(minutes=n))
        )
        for n, text_ in enumerate(texts)
    ]


def test_search_and_of_words(store) -> None:
    conversation = store.create(START)
    said(store, conversation, "Chapter 3 goes to my supervisor",
         "My supervisor is on leave", "Chapter 4 is easier")

    found = store.search("chapter supervisor", 5)

    assert [m.text for m in found] == ["Chapter 3 goes to my supervisor"]


def test_search_excludes_the_current_message(store) -> None:
    conversation = store.create(START)
    first, current = said(store, conversation, "I have a cat", "Do I have a cat?")

    found = store.search("cat", 5, current.id)

    assert [m.id for m in found] == [first.id]


def test_search_quotes_operators(store) -> None:
    conversation = store.create(START)
    said(store, conversation, "a cat OR a dog")

    assert store.search('cat" OR (', 5)[0].text == "a cat OR a dog"
    assert store.search("***", 5) == []


def test_search_follows_conversation_delete(store) -> None:
    conversation = store.create(START)
    said(store, conversation, "Miso is my cat")
    store.delete(conversation.id)

    assert store.search("Miso", 5) == []


def test_deleted_word_not_in_file(path) -> None:
    db = Database.open(path)
    store = SqliteConversationStore(db)
    conversation = store.create(START)
    said(store, conversation, "Zyxquorbelt is a word nobody else says")
    with db.transaction() as connection:
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    assert b"zyxquorbelt" in path.read_bytes().lower()

    store.delete(conversation.id)
    with db.transaction() as connection:
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    db.close()

    files = [path, path.with_name(path.name + "-wal")]
    leftovers = [
        f for f in files if f.exists() and b"zyxquorbelt" in f.read_bytes().lower()
    ]
    assert leftovers == []
