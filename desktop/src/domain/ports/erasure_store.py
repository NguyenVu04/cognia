"""The port through which stored data is erased in groups."""

from __future__ import annotations

from typing import Protocol

from src.domain.erasure.models import Group


class ErasureFailed(Exception):
    """A group could not be counted or erased, with a sentence saying so."""


class ErasureStore(Protocol):
    """Each method raises :class:`ErasureFailed` if it cannot do its work."""

    def count(self, group: Group) -> int:
        """The rows of the group that a person would call items."""
        ...

    def erase(self, group: Group) -> None:
        """Remove the whole group, all of it or none of it."""
        ...

    def compact(self) -> None:
        """Rewrite the file so that no removed row stays in it."""
        ...
