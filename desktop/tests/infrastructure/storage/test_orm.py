from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import (
    Connection,
    Engine,
    create_engine,
    delete,
    event,
    insert,
    inspect,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers

from src.infrastructure.storage import database
from src.infrastructure.storage.database import open_database
from src.infrastructure.storage.orm import (
    Base,
    CharacterProposal,
    CharacterVersion,
    Conversation,
    Event,
    MemoryItem,
    Message,
    Pattern,
    PatternEvidence,
    SpeechDecision,
    outside_orm,
)

NOW = "2026-10-31T12:00:00.000+00:00"

# The parent table of these is emptied only after its children.
UNINDEXED_FOREIGN_KEYS = {
    ("messages", "character_version_id"),
    ("emotion_changes", "character_version_id"),
    ("settings", "character_version_id"),
    ("message_kinds", "streak_reset_seq"),
}


@pytest.fixture
def engine(tmp_path: Path):
    engine = open_database(tmp_path / "cognia.sqlite3")
    yield engine
    engine.dispose()


def add_version(db: Connection, **columns) -> None:
    db.execute(
        insert(CharacterVersion).values(
            **{
                "id": "v1",
                "number": 1,
                "template_id": "yuna",
                "name": "Yuna",
                "role": "Friend",
                "description": "Calm.",
                "appearance_id": "yuna",
                "reactivity": 0.4,
                "feeling_half_life_min": 30.0,
                "mood_half_life_min": 720.0,
                "rest_pleasure": 0.1,
                "rest_arousal": 0.0,
                "rest_dominance": 0.0,
                "origin": "chosen",
                "created_at": NOW,
                **columns,
            }
        )
    )


def add_message(db: Connection, **columns) -> None:
    db.execute(
        insert(Conversation).values(id="c1", title="t", last_active_at=NOW)
    )
    db.execute(
        insert(Message).values(
            **{
                "id": "m1",
                "conversation_id": "c1",
                "role": "user",
                "text": "hi",
                "created_at": NOW,
                **columns,
            }
        )
    )


def add_event(db: Connection, **columns) -> int:
    result = db.execute(
        insert(Event).values(
            **{
                "occurred_at": NOW,
                "utc_offset_min": 420,
                "kind": "presence",
                "payload": "{}",
                **columns,
            }
        )
    )
    return result.inserted_primary_key[0]


def add_decision(db: Connection, id: str, message_id: str | None) -> None:
    db.execute(
        insert(SpeechDecision).values(
            id=id, kind="break", decided_at=NOW, outcome="sent", message_id=message_id
        )
    )


def add_proposal(db: Connection, id: str, result_version_id: str) -> None:
    db.execute(
        insert(CharacterProposal).values(
            id=id,
            base_version_id="v1",
            summary="s",
            fingerprint=id,
            status="approved",
            proposed_at=NOW,
            result_version_id=result_version_id,
        )
    )


@pytest.mark.filterwarnings("ignore:autogenerate skipping")
@pytest.mark.filterwarnings("ignore:Skipped unsupported reflection")
def test_orm_matches_migrations(engine: Engine) -> None:
    with engine.connect() as db:
        context = MigrationContext.configure(
            db,
            opts={
                "include_name": lambda name, type_, parents: not (
                    type_ == "table" and outside_orm(name)
                )
            },
        )
        assert compare_metadata(context, Base.metadata) == []


def test_every_table_is_strict(engine: Engine) -> None:
    with engine.connect() as db:
        tables = db.execute(
            text(
                "SELECT name, sql FROM sqlite_master WHERE type = 'table' "
                "AND name NOT IN ('alembic_version', 'sqlite_sequence')"
            )
        ).all()
    tables = [(name, sql) for name, sql in tables if not outside_orm(name)]

    assert len(tables) == 18
    assert all(sql.rstrip().endswith("STRICT") for _, sql in tables)


def test_mappers_configure() -> None:
    configure_mappers()


def test_noticed_item_needs_reason(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(
            insert(MemoryItem).values(
                id="n1", kind="noticed", text="x", reason=None, recorded_at=NOW
            )
        )


def test_user_message_refuses_version(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as db:
        add_version(db)
        add_message(db, character_version_id="v1")


def test_temperament_range_refused(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as db:
        add_version(db, reactivity=1.5)


def test_restored_is_a_valid_origin(engine: Engine) -> None:
    with engine.begin() as db:
        add_version(db, origin="restored")


def test_removed_origin_refused(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as db:
        add_version(db, origin="written")


def test_template_id_is_required(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as db:
        add_version(db, template_id=None)


def test_event_payload_must_be_json(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as db:
        add_event(db, payload="not json")


def test_delete_event_cascades_evidence(engine: Engine) -> None:
    with engine.begin() as db:
        seq = add_event(db)
        db.execute(
            insert(Pattern).values(
                id="p1",
                rule_id="regular_absence",
                parameters="{}",
                statement="s",
                fingerprint="f",
                found_at=NOW,
            )
        )
        db.execute(insert(PatternEvidence).values(pattern_id="p1", event_seq=seq))
        db.execute(delete(Event).where(Event.seq == seq))

        assert db.execute(select(PatternEvidence)).all() == []
        assert len(db.execute(select(Pattern)).all()) == 1


def test_delete_conversation_keeps_memory(engine: Engine) -> None:
    with engine.begin() as db:
        add_message(db)
        db.execute(
            insert(MemoryItem).values(
                id="i1",
                kind="told",
                text="x",
                source_message_id="m1",
                recorded_at=NOW,
            )
        )
        db.execute(delete(Conversation).where(Conversation.id == "c1"))

        kept = db.execute(select(MemoryItem.source_message_id)).one()
    assert kept.source_message_id is None


def test_decision_outlives_its_message(engine: Engine) -> None:
    with engine.begin() as db:
        add_message(db)
        add_decision(db, "d1", "m1")
        db.execute(delete(Conversation).where(Conversation.id == "c1"))

        kept = db.execute(
            select(SpeechDecision.outcome, SpeechDecision.message_id)
        ).one()
    assert kept.outcome == "sent"
    assert kept.message_id is None


def test_message_has_one_decision(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as db:
        add_message(db)
        add_decision(db, "d1", "m1")
        add_decision(db, "d2", "m1")


def test_version_comes_from_one_proposal(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as db:
        add_version(db)
        add_proposal(db, "a", "v1")
        add_proposal(db, "b", "v1")


def test_foreign_keys_are_indexed() -> None:
    missing = []
    for table in Base.metadata.tables.values():
        leading = {column.name for column in list(table.primary_key.columns)[:1]}
        leading |= {
            list(index.columns)[0].name for index in table.indexes if index.columns
        }
        for key in table.foreign_keys:
            name = (table.name, key.parent.name)
            if key.parent.name not in leading and name not in UNINDEXED_FOREIGN_KEYS:
                missing.append(name)

    assert missing == []


def test_ceiling_query_uses_index(engine: Engine) -> None:
    query = (
        "EXPLAIN QUERY PLAN SELECT count(*) FROM speech_decisions "
        "WHERE decided_at >= '2026' AND kind IN ('remark', 'question', 'break')"
    )
    with engine.connect() as db:
        details = [row[3] for row in db.execute(text(query))]

    assert details
    assert all(detail.startswith("SEARCH") for detail in details)


def test_embedding_is_last_column(engine: Engine) -> None:
    columns = inspect(engine).get_columns

    assert columns("memory_items")[-1]["name"] == "embedding"


# ── revision 0003 ────────────────────────────────────────────────────────


def _migrate(path: Path, revision: str, down: bool = False) -> Engine:
    """A file at ``revision``, with the connection settings of the application."""
    engine = create_engine(f"sqlite:///{path}")
    event.listen(engine, "connect", database._configure)
    event.listen(engine, "begin", database._begin)
    config = Config()
    config.set_main_option("script_location", str(database._MIGRATIONS))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        if down:
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)
    return engine


def _names(engine: Engine, sql: str) -> list:
    with engine.connect() as db:
        return [row[0] for row in db.execute(text(sql))]


def test_0003_removes_old_kinds_and_tables(tmp_path: Path) -> None:
    path = tmp_path / "cognia.sqlite3"
    old = _migrate(path, "0002")
    with old.begin() as db:
        db.execute(text(
            "INSERT INTO events (occurred_at, utc_offset_min, kind, payload) VALUES "
            f"('{NOW}', 0, 'memory_stored', '{{}}'), "
            f"('{NOW}', 0, 'commitment_added', '{{}}')"
        ))
        db.execute(text(
            "INSERT INTO speech_decisions (id, kind, decided_at, outcome) VALUES "
            f"('d1', 'remark', '{NOW}', 'sent'), ('d2', 'commitment', '{NOW}', 'sent')"
        ))
        db.execute(text(
            "INSERT INTO decision_factors (decision_id, position, name, value) "
            "VALUES ('d1', 0, 'observed_seconds', 60.0)"
        ))
    old.dispose()

    engine = _migrate(path, "head")

    assert _names(engine, "SELECT kind FROM events") == ["memory_stored"]
    assert _names(engine, "SELECT id FROM speech_decisions") == ["d1"]
    assert _names(engine, "SELECT name FROM decision_factors") == ["observed_seconds"]
    kinds = _names(engine, "SELECT id FROM message_kinds")
    assert "commitment" not in kinds
    assert "checkin" not in kinds
    tables = set(inspect(engine).get_table_names())
    assert not tables & {"commitments", "message_commitment_refs", "sessions",
                         "session_intents"}
    columns = [c["name"] for c in inspect(engine).get_columns("speech_decisions")]
    assert "session_id" not in columns
    engine.dispose()


def test_0003_downgrade_restores_tables(tmp_path: Path) -> None:
    path = tmp_path / "cognia.sqlite3"
    _migrate(path, "head").dispose()

    engine = _migrate(path, "0002", down=True)

    tables = set(inspect(engine).get_table_names())
    assert {"commitments", "message_commitment_refs", "sessions",
            "session_intents"} <= tables
    columns = [c["name"] for c in inspect(engine).get_columns("speech_decisions")]
    assert "session_id" in columns
    kinds = _names(engine, "SELECT id FROM message_kinds")
    assert {"commitment", "checkin"} <= set(kinds)
    engine.dispose()

    _migrate(path, "head").dispose()


# ── revision 0004 ────────────────────────────────────────────────────────


def test_0004_keeps_messages(tmp_path: Path) -> None:
    path = tmp_path / "cognia.sqlite3"
    old = _migrate(path, "0003")
    with old.begin() as db:
        db.execute(text(
            f"INSERT INTO conversations VALUES ('c1', 'Talk', '{NOW}')"
        ))
        db.execute(text(
            "INSERT INTO messages (id, conversation_id, role, text, created_at) "
            f"VALUES ('m1', 'c1', 'user', 'hi', '{NOW}')"
        ))
    old.dispose()

    engine = _migrate(path, "0004")

    assert _names(engine, "SELECT id FROM messages") == ["m1"]
    assert _names(engine, "SELECT summary_covers FROM conversations") == [0]
    engine.dispose()


def test_0004_downgrade(tmp_path: Path) -> None:
    path = tmp_path / "cognia.sqlite3"
    _migrate(path, "0004").dispose()

    engine = _migrate(path, "0003", down=True)

    columns = [c["name"] for c in inspect(engine).get_columns("conversations")]
    assert "summary" not in columns
    assert "summary_covers" not in columns
    engine.dispose()
    _migrate(path, "head").dispose()


# ── revisions 0005 and 0006 ──────────────────────────────────────────────


def test_0005_indexes_existing_messages(tmp_path: Path) -> None:
    path = tmp_path / "cognia.sqlite3"
    old = _migrate(path, "0004")
    with old.begin() as db:
        db.execute(text(f"INSERT INTO conversations (id, title, last_active_at) "
                        f"VALUES ('c1', 'Talk', '{NOW}')"))
        db.execute(text(
            "INSERT INTO messages (id, conversation_id, role, text, created_at) "
            f"VALUES ('m1', 'c1', 'user', 'Miso is my cat', '{NOW}')"
        ))
    old.dispose()

    engine = _migrate(path, "0005")

    query = "SELECT rowid FROM messages_fts WHERE messages_fts MATCH 'miso'"
    found = _names(engine, query)
    assert len(found) == 1
    engine.dispose()


def test_0005_downgrade(tmp_path: Path) -> None:
    path = tmp_path / "cognia.sqlite3"
    _migrate(path, "0005").dispose()

    engine = _migrate(path, "0004", down=True)

    names = set(_names(engine, "SELECT name FROM sqlite_master"))
    assert not any(name.startswith("messages_fts") for name in names)
    engine.dispose()
    _migrate(path, "head").dispose()


def test_0006_drops_journal(tmp_path: Path) -> None:
    path = tmp_path / "cognia.sqlite3"
    old = _migrate(path, "0005")
    with old.begin() as db:
        db.execute(text(
            "INSERT INTO events (occurred_at, utc_offset_min, kind, payload) VALUES "
            f"('{NOW}', 0, 'memory_stored', '{{}}'), "
            f"('{NOW}', 0, 'reflection_written', '{{}}')"
        ))
    old.dispose()

    engine = _migrate(path, "0006")

    assert _names(engine, "SELECT kind FROM events") == ["memory_stored"]
    tables = set(inspect(engine).get_table_names())
    assert not tables & {"journal_entries", "journal_entry_sources",
                         "message_journal_refs"}
    engine.dispose()


def test_0006_downgrade_restores_tables(tmp_path: Path) -> None:
    path = tmp_path / "cognia.sqlite3"
    _migrate(path, "0006").dispose()

    engine = _migrate(path, "0005", down=True)

    tables = set(inspect(engine).get_table_names())
    assert {"journal_entries", "journal_entry_sources",
            "message_journal_refs"} <= tables
    engine.dispose()
    _migrate(path, "head").dispose()


def test_0007_indexes_event_time(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "cognia.sqlite3", "0007")

    indexes = {i["name"] for i in inspect(engine).get_indexes("events")}
    assert "events_by_time" in indexes
    engine.dispose()
