"""The stores added for speaking up, learning, add-ons and voice settings."""

from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from src.domain.learning.models import FREQUENCY, Adjustment, Pattern
from src.domain.ports.decision_store import DecisionStoreFailed
from src.domain.ports.tool_server_store import ToolServerStoreFailed
from src.domain.speech.models import Factor, MessageKind, Outcome, SpeechSettings
from src.domain.tools.models.tool_server import HTTP, STDIO, ToolServer
from src.infrastructure.storage.app_usage_store import SqliteAppUsage
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.decision_store import SqliteDecisionStore
from src.infrastructure.storage.pattern_store import SqlitePatternStore
from src.infrastructure.storage.settings_store import DEFAULT_HOTKEY, SqliteSettings
from src.infrastructure.storage.tool_server_store import (
    NAME_TAKEN,
    SqliteToolServerStore,
)

AT = datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path: Path):
    opened = Database.open(tmp_path / "cognia.sqlite3")
    yield opened
    opened.close()


def _event(db: Database, seq: int) -> None:
    with db.transaction() as connection:
        connection.execute(
            text(
                "INSERT INTO events (seq, occurred_at, utc_offset_min, kind, payload) "
                f"VALUES ({seq}, '2026-11-09T09:00:00.000+00:00', 0, "
                "'presence', '{}')"
            )
        )


# ── decisions ─────────────────────────────────────────────────────────────


def test_record_and_count_sent(db: Database) -> None:
    store = SqliteDecisionStore(db)
    factors = (Factor("observed_s", 600.0), Factor("mood", 0.1, ref_id=""))

    store.record(MessageKind.BREAK, None, AT, Outcome.SENT, "", factors)
    store.record(MessageKind.REMARK, None, AT, Outcome.WITHHELD, "locked", ())

    assert (
        store.sent_since(
            AT - timedelta(hours=1), [MessageKind.BREAK, MessageKind.REMARK]
        )
        == 1
    )
    assert store.sent_since(AT + timedelta(hours=1), [MessageKind.BREAK]) == 0


def test_factors_kept_in_order(db: Database) -> None:
    store = SqliteDecisionStore(db)
    factors = (Factor("observed_s", 600.0), Factor("threshold_s", 5400.0))

    decision = store.record(MessageKind.BREAK, None, AT, Outcome.SENT, "", factors)

    with db.transaction() as connection:
        rows = connection.execute(
            text(
                "SELECT position, name FROM decision_factors WHERE decision_id = :d "
                "ORDER BY position"
            ),
            {"d": decision},
        ).all()
    assert [tuple(r) for r in rows] == [(0, "observed_s"), (1, "threshold_s")]


def test_respond(db: Database) -> None:
    store = SqliteDecisionStore(db)
    decision = store.record(MessageKind.BREAK, None, AT, Outcome.SENT, "", ())

    store.respond(decision, "postponed")

    with db.transaction() as connection:
        assert (
            connection.execute(text("SELECT response FROM speech_decisions")).scalar()
            == "postponed"
        )


def test_withheld_needs_its_rule(db: Database) -> None:
    with pytest.raises(DecisionStoreFailed):
        SqliteDecisionStore(db).record(
            MessageKind.BREAK, None, AT, Outcome.WITHHELD, "", ()
        )


# ── patterns ──────────────────────────────────────────────────────────────


def test_pattern_round_trip_undo_and_remove(db: Database) -> None:
    for seq in (4, 7, 9):
        _event(db, seq)
    store = SqlitePatternStore(db)
    pattern = Pattern(
        "passed_over_kind", (("kind", "remark"),), (4, 7, 9), "You let them pass."
    )

    learned = store.add(pattern, (Adjustment(FREQUENCY, "1.0", "1.5"),), AT)
    (read,) = store.all()
    undone = store.undo(learned.id, AT)
    removed = store.remove(learned.id)

    assert read.pattern == pattern
    assert not read.undone
    assert undone.undone
    assert removed.id == learned.id
    assert store.all() == []


# ── add-ons ───────────────────────────────────────────────────────────────


def server(name: str = "notes", transport: str = STDIO) -> ToolServer:
    return ToolServer(
        id=f"id-{name}",
        name=name,
        transport=transport,
        command="uvx" if transport == STDIO else "",
        args=("notes-mcp",),
        url="http://127.0.0.1:8000/mcp" if transport == HTTP else "",
        added_at=AT,
        consented_at=AT,
    )


def test_tool_servers_round_trip(db: Database) -> None:
    store = SqliteToolServerStore(db)

    store.add(server())
    store.add(server("web", HTTP))

    assert [s.name for s in store.all()] == ["notes", "web"]
    assert store.all()[0].args == ("notes-mcp",)
    store.remove("id-notes")
    assert [s.name for s in store.all()] == ["web"]


def test_tool_server_name_taken(db: Database) -> None:
    store = SqliteToolServerStore(db)
    store.add(server())

    with pytest.raises(ToolServerStoreFailed, match=NAME_TAKEN):
        store.add(ToolServer("other", "notes", STDIO, "uvx", (), "", AT, AT))


def test_tool_server_needs_a_way_to_reach_it() -> None:
    with pytest.raises(ValueError):
        ToolServer("x", "notes", HTTP, "", (), "ftp://nope", AT, AT)
    with pytest.raises(ValueError):
        ToolServer("x", "notes", STDIO, " ", (), "", AT, AT)


# ── settings ──────────────────────────────────────────────────────────────


def test_voice_defaults(db: Database) -> None:
    settings = SqliteSettings(db)

    assert settings.speak_aloud() is True
    assert settings.talk_hotkey() == DEFAULT_HOTKEY == "Ctrl+Alt+Space"


def test_speech_settings_round_trip(db: Database) -> None:
    settings = SqliteSettings(db)
    chosen = SpeechSettings(
        3, (time(22, 0), time(7, 0)), frozenset({MessageKind.BREAK}), False, 90
    )

    settings.set_speech(chosen)

    assert settings.speech() == chosen


def test_kind_switch(db: Database) -> None:
    settings = SqliteSettings(db)

    settings.set_kind(MessageKind.REMARK, False)

    assert MessageKind.REMARK not in settings.speech().enabled


def test_pause_and_placement(db: Database) -> None:
    settings = SqliteSettings(db)

    settings.set_paused(AT, AT + timedelta(hours=1))
    settings.set_placement(100, 200, "DISPLAY1")
    settings.set_hidden(True)

    assert settings.paused_until() == (AT, AT + timedelta(hours=1), True)
    placement = settings.placement()
    assert (placement.x, placement.y, placement.hidden) == (100, 200, True)
    settings.set_paused(None, None)
    assert settings.paused_until()[2] is False


# ── exclusions ────────────────────────────────────────────────────────────


def test_exclude_deletes_totals_and_include_counts_again(db: Database) -> None:
    usage = SqliteAppUsage(db)
    usage.put("2026-11-09", 9, {"Steam.exe": 30, "Code.exe": 20})

    usage.exclude("Steam.exe")

    assert usage.excluded() == ["Steam.exe"]
    with db.transaction() as connection:
        names = (
            connection.execute(text("SELECT app_name FROM app_usage")).scalars().all()
        )
    assert names == ["Code.exe"]
    usage.include("Steam.exe")
    assert usage.excluded() == []
