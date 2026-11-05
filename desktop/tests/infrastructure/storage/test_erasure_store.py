import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.domain.character.models import CHOSEN, Version
from src.domain.conversation.models import USER, Message
from src.domain.emotion.models import Pad, Temperament
from src.domain.erasure.models import Group
from src.domain.events.models import EventKind
from src.domain.memory.models import TOLD, Commitment, MemoryItem
from src.domain.ports import ErasureFailed
from src.infrastructure.storage import orm
from src.infrastructure.storage.character_store import SqliteCharacterStore
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.erasure_store import (
    GROUP_TABLES,
    NOT_ERASED,
    RESET_TABLES,
    SqliteErasureStore,
)
from src.infrastructure.storage.event_log import SqliteEventLog
from src.infrastructure.storage.memory_store import SqliteMemoryStore
from src.infrastructure.storage.sqlite_store import SqliteConversationStore

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
MARKER = "ZEBRA-7731"


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "cognia.sqlite3"


@pytest.fixture
def db(path: Path):
    database = Database.open(path)
    yield database
    database.close()


@pytest.fixture
def filled(db: Database) -> Database:
    """One row in each group that a store can write today."""
    conversations = SqliteConversationStore(db)
    conversation = conversations.create(NOW)
    message = conversations.append(
        Message.new(conversation.id, USER, f"My code word is {MARKER}", NOW)
    )
    memory = SqliteMemoryStore(db)
    memory.add(MemoryItem(
        id="i1", kind=TOLD, text=f"Code word {MARKER}", reason=None,
        source_message_id=message.id, importance=5, last_retrieved_at=None,
        recorded_at=NOW, embedding=(1.0, 0.0),
    ))
    memory.add(Commitment(
        id="c1", text="Send chapter 3", due_on=None, source_message_id=None,
        importance=8, last_retrieved_at=None, recorded_at=NOW, embedding=None,
    ))
    SqliteEventLog(db).append(NOW, 0, EventKind.MEMORY_STORED,
                              {"memory_item_id": "i1"}, None)
    SqliteCharacterStore(db).add(Version(
        id="v1", number=1, template_id="yuna", name="Yuna", role="Gentle",
        description="You are Yuna.", appearance_id="yuna",
        temperament=Temperament(0.4, 30.0, 720.0, Pad(0.1, 0.0, 0.0)),
        origin=CHOSEN, created_at=NOW,
    ))
    with db.transaction() as connection:
        connection.exec_driver_sql(
            "UPDATE settings SET moods_on = 0, embedding_model = 'm', "
            "chat_device = 'GPU'"
        )
        connection.exec_driver_sql(
            "UPDATE message_kinds SET enabled = 0 WHERE id = 'remark'"
        )
        connection.exec_driver_sql(
            "INSERT INTO app_exclusions (app_name) VALUES ('Bank.exe')"
        )
    return db


def rows(path: Path, sql: str) -> list[tuple]:
    connection = sqlite3.connect(path)
    result = connection.execute(sql).fetchall()
    connection.close()
    return result


def disk_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    wal = path.with_name(path.name + "-wal")
    return data + (wal.read_bytes() if wal.exists() else b"")


def test_every_table_is_erased_or_reset() -> None:
    """A table missing from every group would survive "Erase everything"."""
    grouped = [name for names in GROUP_TABLES.values() for name in names]
    listed = grouped + list(RESET_TABLES)

    assert len(listed) == len(set(listed)), "a table is in two groups"
    assert set(listed) == set(orm.Base.metadata.tables)


def test_counts(filled: Database) -> None:
    store = SqliteErasureStore(filled)

    counts = {group: store.count(group) for group in Group}

    assert counts[Group.CONVERSATIONS] == 1
    assert counts[Group.MEMORY] == 2
    assert counts[Group.EVENTS] == 1
    assert counts[Group.CHARACTER] == 1
    assert counts[Group.SESSIONS] == 0
    assert counts[Group.SETTINGS] == 1


def test_conversations_group_keeps_memory(filled: Database, path: Path) -> None:
    SqliteErasureStore(filled).erase(Group.CONVERSATIONS)

    assert rows(path, "SELECT count(*) FROM messages") == [(0,)]
    assert rows(path, "SELECT source_message_id FROM memory_items") == [(None,)]


def test_memory_level_keeps_character_and_settings(filled, path: Path) -> None:
    store = SqliteErasureStore(filled)
    for group in (Group.CONVERSATIONS, Group.MEMORY, Group.SESSIONS, Group.LEARNING,
                  Group.JOURNAL, Group.SPEECH, Group.EVENTS):
        store.erase(group)

    assert rows(path, "SELECT count(*) FROM memory_items") == [(0,)]
    assert rows(path, "SELECT count(*) FROM events") == [(0,)]
    assert rows(path, "SELECT count(*) FROM character_versions") == [(1,)]
    assert rows(path, "SELECT moods_on, chat_device FROM settings") == [(0, "GPU")]
    assert rows(path, "SELECT count(*) FROM app_exclusions") == [(1,)]


def test_character_group_clears_pointer(filled: Database, path: Path) -> None:
    store = SqliteErasureStore(filled)
    store.erase(Group.CONVERSATIONS)
    store.erase(Group.CHARACTER)

    assert rows(path, "SELECT count(*) FROM character_versions") == [(0,)]
    assert rows(path, "SELECT character_version_id FROM settings") == [(None,)]


def test_settings_group_resets_defaults(filled: Database, path: Path) -> None:
    SqliteErasureStore(filled).erase(Group.SETTINGS)

    assert rows(
        path,
        "SELECT moods_on, awareness_on, embedding_model, chat_device FROM settings",
    ) == [(1, 0, None, None)]
    assert rows(path, "SELECT enabled FROM message_kinds WHERE id = 'remark'") == [
        (1,)
    ]
    assert rows(path, "SELECT count(*) FROM message_kinds") == [(9,)]
    assert rows(path, "SELECT count(*) FROM app_exclusions") == [(0,)]


def test_erase_everything_leaves_no_trace(filled: Database, path: Path) -> None:
    filled.compact()
    assert MARKER.encode() in disk_bytes(path)
    store = SqliteErasureStore(filled)

    for group in Group:
        store.erase(group)
    store.compact()

    assert MARKER.encode() not in disk_bytes(path)


def test_compact_refuses_inside_transaction(db: Database) -> None:
    with db.transaction():
        with pytest.raises(RuntimeError):
            db.compact()


def test_failed_group(filled: Database, path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE decision_factors")
    connection.commit()
    connection.close()

    with pytest.raises(ErasureFailed, match=NOT_ERASED):
        SqliteErasureStore(filled).erase(Group.SPEECH)
