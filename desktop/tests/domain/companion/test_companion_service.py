from collections.abc import Collection, Iterator
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.character.models import CHOSEN, Version
from src.domain.companion import rules
from src.domain.companion.companion_service import CompanionService
from src.domain.companion.models import ShowExpression
from src.domain.emotion.emotion_service import EmotionService
from src.domain.emotion.models import Expression, Pad, Temperament
from src.domain.events.models import Event, EventKind, Payload
from src.domain.ports import CharacterStoreFailed, EventLogFailed

MONDAY = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
V1 = Temperament(0.4, 30.0, 720.0, Pad(0.10, 0.0, 0.0))


def _version() -> Version:
    return Version(
        id="v1",
        number=1,
        template_id="yuna",
        name="Yuna",
        role="The Calm Companion",
        description="You are Yuna.",
        appearance_id="yuna",
        temperament=V1,
        origin=CHOSEN,
        created_at=MONDAY,
    )


class FakeStore:
    def __init__(self, versions: list[Version]) -> None:
        self._versions = versions
        self.failing = False

    def current(self) -> Version | None:
        return self.versions()[0] if self._versions else None

    def versions(self) -> list[Version]:
        if self.failing:
            raise CharacterStoreFailed("history unavailable")
        return list(self._versions)

    def add(self, version: Version) -> Version:
        self._versions.insert(0, version)
        return version

    def close(self) -> None:
        pass


class FakeLog:
    def __init__(self, events: list[Event] | None = None) -> None:
        self.events = list(events or [])
        self._next_seq = len(self.events) + 1
        self.failing = False

    def append(
        self,
        occurred_at: datetime,
        utc_offset_min: int,
        kind: EventKind,
        payload: Payload,
        importance: int | None,
    ) -> Event:
        if self.failing:
            raise EventLogFailed("log unavailable")
        event = Event(
            self._next_seq, occurred_at, utc_offset_min, kind, payload, importance
        )
        self._next_seq += 1
        self.events.append(event)
        return event

    def read_from(self, seq: int) -> Iterator[Event]:
        if self.failing:
            raise EventLogFailed("log unavailable")
        return iter([event for event in self.events if event.seq >= seq])

    def delete(self, seqs: Collection[int]) -> None:
        self.events = [event for event in self.events if event.seq not in seqs]

    def close(self) -> None:
        pass


def _service(log: FakeLog, store: FakeStore | None = None) -> CompanionService:
    return CompanionService(log, EmotionService(store or FakeStore([_version()])))


def test_start_empty_log() -> None:
    assert _service(FakeLog()).start() == rules.initial_state()


def test_start_folds_log() -> None:
    chosen = {"version_id": "v1"}
    later = MONDAY + timedelta(minutes=10)
    log = FakeLog(
        [
            Event(1, MONDAY, 0, EventKind.CHARACTER_CHANGED, chosen, None),
            Event(2, later, 0, EventKind.USER_MESSAGE, {"class": "praise"}, 5),
        ]
    )

    state = _service(log).start()

    assert state.version_id == "v1"
    mood = state.emotion.mood
    assert (mood.pleasure, mood.arousal, mood.dominance) == pytest.approx(
        (0.30, 0.08, 0.04)
    )


def test_record_appends_and_steps() -> None:
    log = FakeLog()
    payload = {"version_id": "v1"}

    result = _service(log).record(
        rules.initial_state(), MONDAY, 60, EventKind.CHARACTER_CHANGED, payload, None
    )

    assert log.events == [
        Event(1, MONDAY, 60, EventKind.CHARACTER_CHANGED, payload, None)
    ]
    assert result.state.version_id == "v1"
    assert result.effects == (ShowExpression(Expression("neutral", 1.0)),)


def test_record_uses_seq_from_log() -> None:
    service = _service(FakeLog())
    first = service.record(
        rules.initial_state(),
        MONDAY,
        0,
        EventKind.CHARACTER_CHANGED,
        {"version_id": "v1"},
        None,
    )

    second = service.record(
        first.state,
        MONDAY + timedelta(minutes=10),
        0,
        EventKind.USER_MESSAGE,
        {"class": "praise"},
        5,
    )

    assert second.state.emotion.computed_to_seq == 2


def test_record_store_failure_appends_nothing() -> None:
    log = FakeLog()
    store = FakeStore([_version()])
    store.failing = True

    with pytest.raises(CharacterStoreFailed):
        _service(log, store).record(
            rules.initial_state(),
            MONDAY,
            0,
            EventKind.CHARACTER_CHANGED,
            {"version_id": "v1"},
            None,
        )

    assert log.events == []


def test_log_failure_passes_through() -> None:
    log = FakeLog()
    log.failing = True

    with pytest.raises(EventLogFailed):
        _service(log).start()
