from datetime import datetime, timezone

import pytest

from src.domain.character.models import CHOSEN, Version
from src.domain.emotion.emotion_service import EmotionService
from src.domain.emotion.models import Pad, Temperament
from src.domain.ports import CharacterStoreFailed

MONDAY = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
MIRA = Temperament(0.6, 45.0, 720.0, Pad(0.25, 0.20, 0.05))
RIN = Temperament(0.3, 30.0, 1440.0, Pad(0.0, -0.10, 0.0))


def _version(version_id: str, number: int, temperament: Temperament) -> Version:
    return Version(
        id=version_id,
        number=number,
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
    def __init__(self, versions: list[Version] | None = None) -> None:
        self._versions = list(versions or [])
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


def test_temperaments_before_first_choice() -> None:
    assert EmotionService(FakeStore()).temperaments() == {}


def test_temperaments_by_version() -> None:
    store = FakeStore([_version("v2", 2, RIN), _version("v1", 1, MIRA)])

    assert EmotionService(store).temperaments() == {"v1": MIRA, "v2": RIN}


def test_store_failure_passes_through() -> None:
    store = FakeStore([_version("v1", 1, MIRA)])
    store.failing = True

    with pytest.raises(CharacterStoreFailed):
        EmotionService(store).temperaments()
