"""The port through which the ready-made characters are read."""

from __future__ import annotations

from typing import Protocol

from src.domain.character.models import Template


class CharacterCatalogUnavailable(Exception):
    """The ready-made characters could not be read, with a sentence saying what
    would fix it. Carries user-facing text."""


class CharacterCatalog(Protocol):
    """The characters the user can choose from."""

    def templates(self) -> list[Template]:
        """Every ready-made character, in the order the picker shows them.

        Raises :class:`CharacterCatalogUnavailable` if they cannot be read.
        """
        ...
