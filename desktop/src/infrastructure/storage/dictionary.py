"""The dictionary that ships with Cognia, read-only.

The file is opened read-only and immutable, so no code path can change it and
SQLite writes nothing beside it. It is opened at the first lookup. A tool can
run on a thread of the tool loop, and one lookup runs at a time, so the
connection is not tied to the thread that opened it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.domain.ports.dictionary import DictionaryUnavailable, Sense

UNAVAILABLE = (
    "The dictionary on this machine cannot be read. Reinstalling Cognia "
    "repairs this."
)


class SqliteDictionary:
    """A :class:`~src.domain.ports.dictionary.Dictionary` over the built file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: sqlite3.Connection | None = None

    def senses(self, word: str) -> list[Sense]:
        try:
            rows = self._open().execute(
                "SELECT pos, definition FROM senses WHERE lemma = ? "
                "ORDER BY pos, rank",
                (word.strip().casefold(),),
            ).fetchall()
        except sqlite3.Error as error:
            raise DictionaryUnavailable(UNAVAILABLE) from error
        return [Sense(pos, definition) for pos, definition in rows]

    def _open(self) -> sqlite3.Connection:
        if self._connection is None:
            if not self._path.is_file():
                raise sqlite3.OperationalError("missing")
            uri = f"{self._path.resolve().as_uri()}?mode=ro&immutable=1"
            self._connection = sqlite3.connect(
                uri, uri=True, check_same_thread=False
            )
        return self._connection
