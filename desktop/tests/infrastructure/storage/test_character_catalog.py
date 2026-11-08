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
voice = "af_heart"
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


def test_every_shipped_character_has_a_known_voice(
    shipped: TomlCharacterCatalog,
) -> None:
    import zipfile

    from src.app import config

    voices = zipfile.ZipFile(config.model_path(config.VOICES)).namelist() if (
        config.model_path(config.VOICES).is_file()
    ) else None
    for template in shipped.templates():
        assert template.voice
        if voices is not None:
            assert f"{template.voice}.npy" in voices


def test_missing_voice_is_unavailable(tmp_path: Path) -> None:
    text = ENTRY.format(reactivity=0.4).replace('voice = "af_heart"', "")

    with pytest.raises(CharacterCatalogUnavailable):
        _written(tmp_path, text).templates()
