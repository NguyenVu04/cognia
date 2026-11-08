"""The ready-made characters, read from the TOML file that ships with Cognia."""

from __future__ import annotations

import tomllib
from pathlib import Path

from src.domain.character.models import Template
from src.domain.emotion.models import Pad, Temperament
from src.domain.ports import CharacterCatalogUnavailable

UNAVAILABLE = (
    "The ready-made characters cannot be read. Reinstalling Cognia repairs this."
)


class TomlCharacterCatalog:
    """A :class:`~src.domain.ports.CharacterCatalog` over ``characters.toml``."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def templates(self) -> list[Template]:
        try:
            text = self._path.read_text(encoding="utf-8")
            return [_template(entry) for entry in tomllib.loads(text)["character"]]
        except (
            OSError,
            tomllib.TOMLDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise CharacterCatalogUnavailable(UNAVAILABLE) from error


def _template(entry: dict) -> Template:
    return Template(
        id=entry["id"],
        name=entry["name"],
        role=entry["role"],
        description=entry["description"],
        appearance_id=entry["appearance"],
        temperament=Temperament(
            reactivity=entry["reactivity"],
            feeling_half_life_min=entry["feeling_half_life_min"],
            mood_half_life_min=entry["mood_half_life_min"],
            rest=Pad(
                entry["rest_pleasure"], entry["rest_arousal"], entry["rest_dominance"]
            ),
        ),
        card_line=entry["card_line"],
        sample_answer=entry["sample_answer"],
        voice=entry["voice"],
    )
