"""The port through which character versions are kept.

It says nothing about SQLite or files: where the versions live is an adapter's
business.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.character.models import Version


class CharacterStoreFailed(Exception):
    """The versions could not be read or saved, with a sentence saying so.

    Carries user-facing text. When the history cannot be read, the user is told
    plainly, rather than shown an empty list as though there had never been one.
    """


class CharacterStore(Protocol):
    """Every version of the one character, and which version is in force.

    Each method raises :class:`CharacterStoreFailed` if it cannot do its work.
    """

    def current(self) -> Version | None:
        """The version in force, or ``None`` if no character has been chosen yet."""
        ...

    def versions(self) -> list[Version]:
        """Every version, newest first."""
        ...

    def add(self, version: Version) -> Version:
        """Record a new version and put it in force, both or neither."""
        ...

    def close(self) -> None:
        """Release whatever the store is holding."""
        ...
