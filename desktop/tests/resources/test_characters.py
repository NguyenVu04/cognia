import tomllib

import pytest

from src.utils.paths import resource

FIELDS = {
    "id",
    "name",
    "role",
    "description",
    "appearance",
    "reactivity",
    "feeling_half_life_min",
    "mood_half_life_min",
    "rest_pleasure",
    "rest_arousal",
    "rest_dominance",
    "card_line",
    "sample_answer",
    "voice",
}
TEMPERAMENT = (
    "reactivity",
    "feeling_half_life_min",
    "mood_half_life_min",
    "rest_pleasure",
    "rest_arousal",
    "rest_dominance",
)
REST = ("rest_pleasure", "rest_arousal", "rest_dominance")


def _characters() -> list[dict]:
    text = resource("characters.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)["character"]


CHARACTERS = _characters()


def test_four_characters_in_order() -> None:
    assert [c["id"] for c in CHARACTERS] == ["yuna", "rin", "mira", "shiori"]


@pytest.mark.parametrize("character", CHARACTERS, ids=lambda c: c["id"])
def test_every_character_has_every_field(character: dict) -> None:
    assert set(character) == FIELDS


# The same ranges as the CHECK constraints on character_versions.
@pytest.mark.parametrize("character", CHARACTERS, ids=lambda c: c["id"])
def test_temperament_in_range(character: dict) -> None:
    assert 0 <= character["reactivity"] <= 1
    assert character["feeling_half_life_min"] > 0
    assert character["mood_half_life_min"] > 0
    for column in REST:
        assert -1 <= character[column] <= 1


# tomllib reads 30 as an int; the columns are REAL.
@pytest.mark.parametrize("character", CHARACTERS, ids=lambda c: c["id"])
def test_temperament_values_are_floats(character: dict) -> None:
    for column in TEMPERAMENT:
        assert isinstance(character[column], float), column


# A card shows one line of the sample answer.
@pytest.mark.parametrize("character", CHARACTERS, ids=lambda c: c["id"])
def test_card_line_is_in_sample_answer(character: dict) -> None:
    assert character["card_line"] in character["sample_answer"]


@pytest.mark.parametrize("character", CHARACTERS, ids=lambda c: c["id"])
def test_text_has_no_outer_whitespace(character: dict) -> None:
    for column in ("description", "sample_answer"):
        assert character[column] == character[column].strip(), column
