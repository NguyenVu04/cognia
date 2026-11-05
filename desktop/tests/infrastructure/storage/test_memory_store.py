import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.domain.conversation.models import COMPANION, USER, Message
from src.domain.memory.models import TOLD, Commitment, MemoryItem
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


def commitment(id: str = "c1", due: date | None = None, hours: int = 0) -> Commitment:
    return Commitment(
        id=id, text="Send chapter 3", due_on=due, source_message_id=None,
        importance=8, last_retrieved_at=None,
        recorded_at=NOW + timedelta(hours=hours), embedding=None,
    )


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


def test_commitment_order(store: SqliteMemoryStore) -> None:
    store.add(commitment("late", due=date(2026, 11, 20)))
    store.add(commitment("none-b", hours=2))
    store.add(commitment("soon", due=date(2026, 11, 6)))
    store.add(commitment("none-a", hours=1))

    assert [c.id for c in store.commitments()] == ["soon", "late", "none-a", "none-b"]


def test_due_on_stored_as_day(store: SqliteMemoryStore, path: Path) -> None:
    store.add(commitment(due=date(2026, 11, 6)))

    connection = sqlite3.connect(path)
    assert connection.execute("SELECT due_on FROM commitments").fetchall() == [
        ("2026-11-06",)
    ]
    connection.close()


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
    told, said = item(), commitment()
    store.add(told)
    store.add(said)
    later = NOW + timedelta(hours=3)

    store.link(reply.id, [told, said], later)

    assert count(path, "message_memory_refs") == 1
    assert count(path, "message_commitment_refs") == 1
    assert store.items()[0].last_retrieved_at == later
    assert store.commitments()[0].last_retrieved_at == later


def test_set_embedding(store: SqliteMemoryStore) -> None:
    stored = commitment()
    store.add(stored)

    store.set_embedding(stored, (0.5, 0.5))

    assert store.commitments()[0].embedding == (0.5, 0.5)


def test_embedding_model_none_on_new_file(store: SqliteMemoryStore) -> None:
    assert store.embedding_model() is None


def test_reset_embeddings(store: SqliteMemoryStore) -> None:
    store.add(item(embedding=(1.0,)))
    store.add(commitment())
    store.set_embedding(store.commitments()[0], (1.0,))

    store.reset_embeddings("embedding.gguf:36685152")

    assert store.items()[0].embedding is None
    assert store.commitments()[0].embedding is None
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
