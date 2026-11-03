from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.domain.character import rules
from src.domain.character.models import CHOSEN, RESTORED, Template
from src.domain.emotion.models import Pad, Temperament

MONDAY = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
TUESDAY = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
WEDNESDAY = datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc)


def _template(template_id: str, name: str, reactivity: float) -> Template:
    return Template(
        id=template_id,
        name=name,
        role=f"The {name} role",
        description=f"You are {name}.",
        appearance_id=template_id,
        temperament=Temperament(reactivity, 30.0, 720.0, Pad(0.1, 0.0, 0.0)),
        card_line=f"{name} line",
        sample_answer=f"{name} answer. {name} line",
    )


YUNA = _template("yuna", "Yuna", 0.4)
RIN = _template("rin", "Rin", 0.6)


@pytest.fixture
def two() -> list:
    """Yuna chosen on Monday, Rin on Tuesday."""
    v1 = rules.from_template(YUNA, [], "v1", MONDAY)
    v2 = rules.from_template(RIN, [v1], "v2", TUESDAY)
    return [v1, v2]


def test_next_number_empty() -> None:
    assert rules.next_number([]) == 1


def test_next_number_after_three() -> None:
    v1 = rules.from_template(YUNA, [], "v1", MONDAY)
    history = [replace(v1, number=3), v1, replace(v1, number=2)]

    assert rules.next_number(history) == 4


def test_from_template_first() -> None:
    version = rules.from_template(YUNA, [], "v1", MONDAY)

    assert version.id == "v1"
    assert version.number == 1
    assert version.origin == CHOSEN
    assert version.created_at == MONDAY
    assert version.template_id == "yuna"
    assert version.name == YUNA.name
    assert version.role == YUNA.role
    assert version.description == YUNA.description
    assert version.appearance_id == YUNA.appearance_id
    assert version.temperament == YUNA.temperament


def test_from_template_change(two: list) -> None:
    assert two[1].number == 2
    assert two[1].template_id == "rin"


def test_from_template_in_force_refused() -> None:
    v1 = rules.from_template(YUNA, [], "v1", MONDAY)

    with pytest.raises(ValueError):
        rules.from_template(YUNA, [v1], "v2", TUESDAY)


def test_restored_copies_earlier(two: list) -> None:
    v1 = two[0]
    version = rules.restored(v1, two, "v3", WEDNESDAY)

    assert version.id == "v3"
    assert version.number == 3
    assert version.origin == RESTORED
    assert version.created_at == WEDNESDAY
    assert replace(version, id="v1", number=1, origin=CHOSEN, created_at=MONDAY) == v1


def test_restored_in_force_refused(two: list) -> None:
    with pytest.raises(ValueError):
        rules.restored(two[1], two, "v3", WEDNESDAY)


def test_restored_not_in_history(two: list) -> None:
    stranger = replace(two[0], id="other")

    with pytest.raises(ValueError):
        rules.restored(stranger, two, "v3", WEDNESDAY)


def test_in_force_until_current(two: list) -> None:
    assert rules.in_force_until(two[1], two) is None


def test_in_force_until_earlier(two: list) -> None:
    assert rules.in_force_until(two[0], two) == TUESDAY
