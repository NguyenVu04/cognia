from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, delete, insert, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from src.infrastructure.storage.database import open_database
from src.infrastructure.storage.orm import (
    Base,
    CharacterProposalRow,
    CharacterVersionRow,
    ConversationRow,
    EventRow,
    MemoryItemRow,
    MessageRow,
    PatternEvidenceRow,
    PatternRow,
    SessionRow,
    SpeechDecisionRow,
)

NOW = "2026-10-31T12:00:00.000+00:00"

# The parent table of these is emptied only after its children (ERD section 14).
UNINDEXED_FOREIGN_KEYS = {
    ("messages", "character_version_id"),
    ("journal_entries", "character_version_id"),
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
        insert(CharacterVersionRow).values(
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
        insert(ConversationRow).values(id="c1", title="t", last_active_at=NOW)
    )
    db.execute(
        insert(MessageRow).values(
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
        insert(EventRow).values(
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
        insert(SpeechDecisionRow).values(
            id=id, kind="break", decided_at=NOW, outcome="sent", message_id=message_id
        )
    )


def add_proposal(db: Connection, id: str, result_version_id: str) -> None:
    db.execute(
        insert(CharacterProposalRow).values(
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
        context = MigrationContext.configure(db)
        assert compare_metadata(context, Base.metadata) == []


def test_every_table_is_strict(engine: Engine) -> None:
    with engine.connect() as db:
        tables = db.execute(
            text(
                "SELECT name, sql FROM sqlite_master WHERE type = 'table' "
                "AND name NOT IN ('alembic_version', 'sqlite_sequence')"
            )
        ).all()

    assert len(tables) == 25
    assert all(sql.rstrip().endswith("STRICT") for _, sql in tables)


def test_mappers_configure() -> None:
    configure_mappers()


def test_second_open_session_refused(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(insert(SessionRow).values(id="s1", started_at=NOW))
        db.execute(insert(SessionRow).values(id="s2", started_at=NOW))


def test_noticed_item_needs_reason(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(
            insert(MemoryItemRow).values(
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
            insert(PatternRow).values(
                id="p1",
                rule_id="regular_absence",
                parameters="{}",
                statement="s",
                fingerprint="f",
                found_at=NOW,
            )
        )
        db.execute(insert(PatternEvidenceRow).values(pattern_id="p1", event_seq=seq))
        db.execute(delete(EventRow).where(EventRow.seq == seq))

        assert db.execute(select(PatternEvidenceRow)).all() == []
        assert len(db.execute(select(PatternRow)).all()) == 1


def test_delete_conversation_keeps_memory(engine: Engine) -> None:
    with engine.begin() as db:
        add_message(db)
        db.execute(
            insert(MemoryItemRow).values(
                id="i1",
                kind="told",
                text="x",
                source_message_id="m1",
                recorded_at=NOW,
            )
        )
        db.execute(delete(ConversationRow).where(ConversationRow.id == "c1"))

        kept = db.execute(select(MemoryItemRow.source_message_id)).one()
    assert kept.source_message_id is None


def test_decision_outlives_its_message(engine: Engine) -> None:
    with engine.begin() as db:
        add_message(db)
        add_decision(db, "d1", "m1")
        db.execute(delete(ConversationRow).where(ConversationRow.id == "c1"))

        kept = db.execute(
            select(SpeechDecisionRow.outcome, SpeechDecisionRow.message_id)
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

    for table in ("memory_items", "commitments", "journal_entries"):
        assert columns(table)[-1]["name"] == "embedding"


def test_embedding_is_deferred(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(
            MemoryItemRow(
                id="i1", kind="told", text="x", recorded_at=NOW, embedding=b"\0"
            )
        )
        session.commit()

    with Session(engine) as session:
        item = session.get(MemoryItemRow, "i1")
        assert "embedding" in inspect(item).unloaded
