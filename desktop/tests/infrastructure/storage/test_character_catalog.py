from pathlib import Path

import pytest

from src.domain.emotion.models import Pad, Temperament
from src.domain.ports import CharacterCatalogUnavailable
from src.infrastructure.storage.character_catalog import TomlCharacterCatalog
from src.utils.paths import resource

ENTRY = """
[[character]]
id = "yuna"
name = "Yuna"
role = "The Gentle Companion"
description = "You are Yuna."
appearance = "yuna"
reactivity = {reactivity}
feeling_half_life_min = 30.0
mood_half_life_min = 720.0
rest_pleasure = 0.10
rest_arousal = -0.05
rest_dominance = 0.00
card_line = "Hi."
sample_answer = "Hi."
"""


@pytest.fixture
def shipped() -> TomlCharacterCatalog:
    return TomlCharacterCatalog(resource("characters.toml"))


def _written(tmp_path: Path, text: str) -> TomlCharacterCatalog:
    path = tmp_path / "characters.toml"
    path.write_text(text, encoding="utf-8")
    return TomlCharacterCatalog(path)


def test_shipped_file_four_in_order(shipped: TomlCharacterCatalog) -> None:
    ids = [t.id for t in shipped.templates()]

    assert ids == ["yuna", "rin", "mira", "shiori"]


def test_yuna_temperament(shipped: TomlCharacterCatalog) -> None:
    yuna = shipped.templates()[0]

    assert yuna.temperament == Temperament(0.4, 30.0, 720.0, Pad(0.10, -0.05, 0.00))


def test_appearance_maps_to_appearance_id(tmp_path: Path) -> None:
    catalog = _written(tmp_path, ENTRY.format(reactivity=0.4))

    assert catalog.templates()[0].appearance_id == "yuna"


def test_missing_file(tmp_path: Path) -> None:
    catalog = TomlCharacterCatalog(tmp_path / "none.toml")

    with pytest.raises(CharacterCatalogUnavailable):
        catalog.templates()


def test_malformed_toml(tmp_path: Path) -> None:
    catalog = _written(tmp_path, "[[character")

    with pytest.raises(CharacterCatalogUnavailable):
        catalog.templates()


def test_out_of_range_temperament(tmp_path: Path) -> None:
    catalog = _written(tmp_path, ENTRY.format(reactivity=1.5))

    with pytest.raises(CharacterCatalogUnavailable):
        catalog.templates()
