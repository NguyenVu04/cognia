"""The port through which the meaning of an English word is read."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Sense:
    """One meaning of a word: its part of speech, in words, and its definition."""

    pos: str
    definition: str


class DictionaryUnavailable(Exception):
    """The dictionary cannot be read, with a sentence saying so."""


class Dictionary(Protocol):
    """A dictionary that ships with Cognia and is never written to."""

    def senses(self, word: str) -> list[Sense]:
        """The meanings of ``word``, most common first within each part of
        speech; empty if it has none. Raises :class:`DictionaryUnavailable`."""
        ...
