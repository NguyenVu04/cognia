import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.domain.events.models import EventKind
from src.domain.ports import EventLogFailed
from src.infrastructure.storage import event_log
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.event_log import SqliteEventLog

MONDAY = datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "cognia.sqlite3"


@pytest.fixture
def log(path: Path):
    db = Database.open(path)
    yield SqliteEventLog(db)
    db.close()


def _presence(log: SqliteEventLog, minutes: int = 0):
    return log.append(
        MONDAY + timedelta(minutes=minutes), 420, EventKind.PRESENCE, {}, None
    )


def _seqs(log: SqliteEventLog, seq: int = 1) -> list[int]:
    return [event.seq for event in log.read_from(seq)]


def _column(path: Path, column: str) -> str:
    db = sqlite3.connect(path)
    value = db.execute(f"SELECT {column} FROM events").fetchone()[0]
    db.close()
    return value


def test_new_log_is_empty(log: SqliteEventLog) -> None:
    assert list(log.read_from(1)) == []


def test_append_gives_seq_from_one(log: SqliteEventLog) -> None:
    assert [_presence(log).seq, _presence(log).seq] == [1, 2]


def test_round_trip_all_fields(log: SqliteEventLog) -> None:
    payload = {"app": "Trình duyệt", "minutes": 42, "share": 0.25, "at_desk": True}
    at = datetime(2026, 11, 2, 1, 0, 0, 125678, tzinfo=timezone.utc)

    event = log.append(at, 60, EventKind.APP_HOUR_CLOSED, payload, 7)

    assert list(log.read_from(1)) == [event]
    assert event.occurred_at == at.replace(microsecond=125000)


def test_append_stores_utc(log: SqliteEventLog, path: Path) -> None:
    at = datetime(2026, 11, 2, 8, 0, tzinfo=timezone(timedelta(hours=7)))

    event = log.append(at, 420, EventKind.PRESENCE, {}, None)

    assert _column(path, "occurred_at") == "2026-11-02T01:00:00.000+00:00"
    assert event.occurred_at == at


def test_payload_readable_json(log: SqliteEventLog, path: Path) -> None:
    payload = {"confidence": 0.9, "class": "praise"}

    log.append(MONDAY, 0, EventKind.USER_MESSAGE, payload, 5)

    assert _column(path, "payload") == '{"class": "praise", "confidence": 0.9}'


def test_seq_list_round_trip(log: SqliteEventLog) -> None:
    payload = {"fingerprint": "regular_absence|hour=11", "evidence": (410, 522, 633)}

    event = log.append(MONDAY, 0, EventKind.PATTERN_REJECTED, payload, None)

    assert event.payload == payload
    assert list(log.read_from(1)) == [event]


def test_seq_list_stored_as_json_array(log: SqliteEventLog, path: Path) -> None:
    payload = {"fingerprint": "regular_absence|hour=11", "evidence": (410, 522, 633)}

    log.append(MONDAY, 0, EventKind.PATTERN_REJECTED, payload, None)

    assert _column(path, "payload") == (
        '{"evidence": [410, 522, 633], "fingerprint": "regular_absence|hour=11"}'
    )


def test_read_from_middle(log: SqliteEventLog) -> None:
    for minutes in range(3):
        _presence(log, minutes)

    assert _seqs(log, 2) == [2, 3]


def test_read_from_past_end(log: SqliteEventLog) -> None:
    _presence(log)

    assert _seqs(log, 10) == []


def test_read_from_across_pages(
    log: SqliteEventLog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(event_log, "_PAGE", 2)
    for minutes in range(5):
        _presence(log, minutes)

    assert _seqs(log) == [1, 2, 3, 4, 5]


def test_delete_removes_events(log: SqliteEventLog) -> None:
    for minutes in range(3):
        _presence(log, minutes)

    log.delete({2})

    assert _seqs(log) == [1, 3]


def test_delete_nothing(log: SqliteEventLog) -> None:
    _presence(log)

    log.delete([])

    assert _seqs(log) == [1]


def test_delete_many_seqs(log: SqliteEventLog) -> None:
    for minutes in range(3):
        _presence(log, minutes)

    log.delete(range(1, 1001))

    assert _seqs(log) == []


def test_seq_never_reused(log: SqliteEventLog) -> None:
    for minutes in range(3):
        _presence(log, minutes)
    log.delete({3})

    assert _presence(log, 3).seq == 4


def test_importance_out_of_range(log: SqliteEventLog) -> None:
    with pytest.raises(EventLogFailed):
        log.append(MONDAY, 0, EventKind.USER_MESSAGE, {"class": "praise"}, 11)

    assert _seqs(log) == []


def test_unknown_kind_unreadable(log: SqliteEventLog, path: Path) -> None:
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO events (occurred_at, utc_offset_min, kind, payload, importance)"
        " VALUES ('2026-11-02T01:00:00.000+00:00', 0, 'sarcasm', '{}', NULL)"
    )
    db.commit()
    db.close()

    with pytest.raises(EventLogFailed):
        list(log.read_from(1))


def test_unreadable_log(log: SqliteEventLog, path: Path) -> None:
    _presence(log)
    db = sqlite3.connect(path)
    db.execute("ALTER TABLE events RENAME TO lost")
    db.commit()
    db.close()

    with pytest.raises(EventLogFailed):
        list(log.read_from(1))
    with pytest.raises(EventLogFailed):
        _presence(log)
    with pytest.raises(EventLogFailed):
        log.delete({1})


def test_read_since_filters_and_orders(log) -> None:
    from datetime import timedelta

    from src.domain.events.models import EventKind

    start = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
    for minutes in (0, 10, 20):
        log.append(start + timedelta(minutes=minutes), 0, EventKind.PRESENCE, {}, None)

    found = list(log.read_since(start + timedelta(minutes=10)))

    assert [e.occurred_at for e in found] == [
        start + timedelta(minutes=10), start + timedelta(minutes=20)
    ]
