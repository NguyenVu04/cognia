from datetime import datetime, timedelta, timezone

import pytest

from src.domain.character.models import CHOSEN, Version
from src.domain.emotion.emotion_service import EmotionService
from src.domain.emotion.models import Pad, Temperament
from src.domain.events.models import Event, EventKind
from src.domain.ports import CharacterStoreFailed

MONDAY = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
MIRA_REST = Pad(0.25, 0.20, 0.05)
MIRA = Temperament(0.6, 45.0, 720.0, MIRA_REST)


def _version(temperament: Temperament) -> Version:
    return Version(
        id="v1",
        number=1,
        template_id="mira",
        name="Mira",
        role="The Energetic Companion",
        description="You are Mira.",
        appearance_id="mira",
        temperament=temperament,
        origin=CHOSEN,
        created_at=MONDAY,
    )


class FakeStore:
    def __init__(self, version: Version | None = None) -> None:
        self.version = version
        self.failing = False

    def current(self) -> Version | None:
        if self.failing:
            raise CharacterStoreFailed("history unavailable")
        return self.version

    def versions(self) -> list[Version]:
        return [self.version] if self.version else []

    def add(self, version: Version) -> Version:
        self.version = version
        return version

    def close(self) -> None:
        pass


def _praise(seq: int = 1, at: datetime = MONDAY) -> Event:
    return Event(seq, at, 0, EventKind.USER_MESSAGE, {"class": "praise"}, None)


def _axes(point: Pad) -> tuple[float, float, float]:
    return (point.pleasure, point.arousal, point.dominance)


def test_resting_before_first_choice() -> None:
    assert EmotionService(FakeStore()).resting(MONDAY) is None


def test_resting_uses_version_in_force() -> None:
    state = EmotionService(FakeStore(_version(MIRA))).resting(MONDAY)

    assert state is not None
    assert state.mood == MIRA_REST


def test_feel_uses_version_in_force() -> None:
    service = EmotionService(FakeStore(_version(MIRA)))
    state = service.resting(MONDAY)
    assert state is not None

    state = service.feel(state, _praise())

    assert _axes(state.mood) == pytest.approx((0.55, 0.32, 0.11))


def test_feel_without_character() -> None:
    service = EmotionService(FakeStore(_version(MIRA)))
    state = service.resting(MONDAY)
    assert state is not None

    with pytest.raises(ValueError):
        EmotionService(FakeStore()).feel(state, _praise())


def test_feel_moods_off() -> None:
    service = EmotionService(FakeStore(_version(MIRA)))
    state = service.resting(MONDAY)
    assert state is not None
    state = service.feel(state, _praise())

    state = service.feel(
        state, _praise(seq=2, at=MONDAY + timedelta(minutes=1)), moods_on=False
    )

    assert state.mood == MIRA_REST
    assert state.feeling == Pad(0.0, 0.0, 0.0)
    assert state.computed_to_seq == 2


def test_store_failure_passes_through() -> None:
    store = FakeStore(_version(MIRA))
    service = EmotionService(store)
    state = service.resting(MONDAY)
    assert state is not None
    store.failing = True

    with pytest.raises(CharacterStoreFailed):
        service.feel(state, _praise())
