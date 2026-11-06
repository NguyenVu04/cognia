import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.domain.conversation.models import COMPANION, USER, Message
from src.domain.memory.models import TOLD, MemoryItem
from src.domain.ports import MemoryStoreFailed
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.memory_store import (
    NOT_SAVED,
    UNREADABLE,
    SqliteMemoryStore,
)
from src.infrastructure.storage.sqlite_store import SqliteConversationStore

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)


def item(id: str = "i1", hours: int = 0, **fields) -> MemoryItem:
    values = dict(
        id=id, kind=TOLD, text="Is writing a thesis", reason=None,
        source_message_id=None, importance=7, last_retrieved_at=None,
        recorded_at=NOW + timedelta(hours=hours), embedding=None,
    )
    values.update(fields)
    return MemoryItem(**values)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "cognia.sqlite3"


@pytest.fixture
def db(path: Path):
    database = Database.open(path)
    yield database
    database.close()


@pytest.fixture
def store(db: Database) -> SqliteMemoryStore:
    return SqliteMemoryStore(db)


@pytest.fixture
def reply(db: Database) -> Message:
    """A user message and the companion reply after it."""
    conversations = SqliteConversationStore(db)
    conversation = conversations.create(NOW)
    conversations.append(Message.new(conversation.id, USER, "Hi", NOW))
    return conversations.append(Message.new(conversation.id, COMPANION, "Hello", NOW))


def count(path: Path, table: str) -> int:
    connection = sqlite3.connect(path)
    (total,) = connection.execute(f"SELECT count(*) FROM {table}").fetchone()
    connection.close()
    return total


def test_round_trip_with_vector(store: SqliteMemoryStore) -> None:
    stored = item(embedding=(1.0, -0.5, 0.25), last_retrieved_at=NOW)
    store.add(stored)

    assert store.items() == [stored]


def test_items_newest_first(store: SqliteMemoryStore) -> None:
    store.add(item("old", hours=0))
    store.add(item("new", hours=1))

    assert [i.id for i in store.items()] == ["new", "old"]


def test_correct_drops_vector(store: SqliteMemoryStore) -> None:
    stored = item(embedding=(1.0, 0.0))
    store.add(stored)

    store.correct(stored, "Works on a thesis")

    (changed,) = store.items()
    assert (changed.text, changed.embedding) == ("Works on a thesis", None)


def test_remove_takes_refs(store: SqliteMemoryStore, reply: Message, path) -> None:
    stored = item()
    store.add(stored)
    store.link(reply.id, [stored], NOW)

    store.remove(stored)

    assert store.items() == []
    assert count(path, "message_memory_refs") == 0


def test_link_writes_refs_and_use(store: SqliteMemoryStore, reply, path) -> None:
    first, second = item("i1"), item("i2", hours=1)
    store.add(first)
    store.add(second)
    later = NOW + timedelta(hours=3)

    store.link(reply.id, [first, second], later)

    assert count(path, "message_memory_refs") == 2
    assert [i.last_retrieved_at for i in store.items()] == [later, later]


def test_link_nothing(store: SqliteMemoryStore, reply, path) -> None:
    store.link(reply.id, [], NOW)

    assert count(path, "message_memory_refs") == 0


def test_set_embedding(store: SqliteMemoryStore) -> None:
    stored = item()
    store.add(stored)

    store.set_embedding(stored, (0.5, 0.5))

    assert store.items()[0].embedding == (0.5, 0.5)


def test_embedding_model_none_on_new_file(store: SqliteMemoryStore) -> None:
    assert store.embedding_model() is None


def test_reset_embeddings(store: SqliteMemoryStore) -> None:
    store.add(item(embedding=(1.0,)))

    store.reset_embeddings("embedding.gguf:36685152")

    assert store.items()[0].embedding is None
    assert store.embedding_model() == "embedding.gguf:36685152"


def test_add_joins_failing_outer_transaction(store: SqliteMemoryStore, db) -> None:
    with pytest.raises(RuntimeError):
        with db.transaction():
            store.add(item())
            raise RuntimeError("the reply could not be saved")

    assert store.items() == []


def test_unreadable(store: SqliteMemoryStore, path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE memory_item_evidence")
    connection.execute("DROP TABLE message_memory_refs")
    connection.execute("DROP TABLE memory_items")
    connection.commit()
    connection.close()

    with pytest.raises(MemoryStoreFailed, match=UNREADABLE):
        store.items()


def test_not_saved(store: SqliteMemoryStore) -> None:
    store.add(item())

    with pytest.raises(MemoryStoreFailed, match=NOT_SAVED):
        store.add(item())
