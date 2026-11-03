from datetime import datetime, timezone

import pytest

from src.domain.character.character_service import CharacterService
from src.domain.character.models import Template, Version
from src.domain.emotion.models import Pad, Temperament
from src.domain.ports import CharacterStoreFailed

MONDAY = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
TUESDAY = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
WEDNESDAY = datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc)


def _template(template_id: str, name: str) -> Template:
    return Template(
        id=template_id,
        name=name,
        role=f"The {name} role",
        description=f"You are {name}.",
        appearance_id=template_id,
        temperament=Temperament(0.4, 30.0, 720.0, Pad(0.1, 0.0, 0.0)),
        card_line=f"{name} line",
        sample_answer=f"{name} answer. {name} line",
    )


TEMPLATES = [_template("yuna", "Yuna"), _template("rin", "Rin")]


class FakeStore:
    def __init__(self) -> None:
        self.stored: list[Version] = []
        self.failing = False

    def current(self) -> Version | None:
        return self.versions()[0] if self.stored else None

    def versions(self) -> list[Version]:
        if self.failing:
            raise CharacterStoreFailed("history unavailable")
        return sorted(self.stored, key=lambda v: v.number, reverse=True)

    def add(self, version: Version) -> Version:
        self.stored.append(version)
        return version

    def close(self) -> None:
        pass


class FakeCatalog:
    def templates(self) -> list[Template]:
        return list(TEMPLATES)


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def service(store: FakeStore) -> CharacterService:
    return CharacterService(store, FakeCatalog())


def test_current_none_before_first_run(service: CharacterService) -> None:
    assert service.current() is None


def test_choose_first_run(service: CharacterService) -> None:
    service.choose("yuna", MONDAY)

    assert service.current().number == 1
    assert service.current().template_id == "yuna"


def test_choose_unknown_id(service: CharacterService, store: FakeStore) -> None:
    with pytest.raises(ValueError):
        service.choose("kes", MONDAY)

    assert store.stored == []


def test_choose_in_force_refused(service: CharacterService, store: FakeStore) -> None:
    service.choose("yuna", MONDAY)

    with pytest.raises(ValueError):
        service.choose("yuna", TUESDAY)

    assert len(store.stored) == 1


def test_choose_another(service: CharacterService) -> None:
    service.choose("yuna", MONDAY)
    service.choose("rin", TUESDAY)

    assert [v.number for v in service.history()] == [2, 1]


def test_restore_brings_back_earlier(service: CharacterService) -> None:
    first = service.choose("yuna", MONDAY)
    service.choose("rin", TUESDAY)

    service.restore(first.id, WEDNESDAY)

    assert service.current().template_id == "yuna"
    assert service.current().number == 3
    assert len(service.history()) == 3


def test_restore_unknown_id(service: CharacterService) -> None:
    service.choose("yuna", MONDAY)

    with pytest.raises(ValueError):
        service.restore("nope", TUESDAY)


def test_history_failure_passes_through(
    service: CharacterService, store: FakeStore
) -> None:
    store.failing = True

    with pytest.raises(CharacterStoreFailed, match="history unavailable"):
        service.history()


def test_templates_from_catalog(service: CharacterService) -> None:
    assert service.templates() == TEMPLATES
