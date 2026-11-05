"""Keeping what the user said, correcting it, removing it, and using it."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime

from src.domain.memory.models import (
    TOLD,
    Commitment,
    Entry,
    MemoryItem,
    Selection,
    Vector,
)
from src.domain.memory.rules import tidy
from src.domain.ports import MemoryStore


class MemoryService:
    """The lines the companion remembers about the user.

    The time is handed in. Exceptions from the port pass through unchanged. The
    caller writes the matching events in the same transaction.
    """

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def entries(self) -> list[Entry]:
        """Every remembered line and every commitment."""
        return [*self._store.items(), *self._store.commitments()]

    def remember(
        self,
        chosen: Selection,
        importance: int,
        source_message_id: str,
        vectors: Mapping[str, Vector],
        now: datetime,
    ) -> tuple[Entry, ...]:
        """Store the chosen lines as said by the user in that message, and return
        them. ``vectors`` holds the vector of a line by its text, if known."""
        stored: list[Entry] = []
        for text in chosen.facts:
            stored.append(
                MemoryItem(
                    id=uuid.uuid4().hex,
                    kind=TOLD,
                    text=text,
                    reason=None,
                    source_message_id=source_message_id,
                    importance=importance,
                    last_retrieved_at=None,
                    recorded_at=now,
                    embedding=vectors.get(text),
                )
            )
        for said in chosen.commitments:
            stored.append(
                Commitment(
                    id=uuid.uuid4().hex,
                    text=said.text,
                    due_on=said.due_on,
                    source_message_id=source_message_id,
                    importance=importance,
                    last_retrieved_at=None,
                    recorded_at=now,
                    embedding=vectors.get(said.text),
                )
            )
        for entry in stored:
            self._store.add(entry)
        return tuple(stored)

    def correct(self, entry: Entry, text: str) -> None:
        """Replace the words. Its vector is computed again later. Raises
        ``ValueError`` for blank text."""
        line = tidy(text)
        if not line:
            raise ValueError("A remembered line needs words.")
        self._store.correct(entry, line)

    def remove(self, entry: Entry) -> None:
        self._store.remove(entry)

    def use(self, message_id: str, entries: Sequence[Entry], now: datetime) -> None:
        """Record that the reply ``message_id`` drew on ``entries``."""
        if entries:
            self._store.link(message_id, entries, now)

    def store_vector(self, entry: Entry, vector: Vector) -> None:
        self._store.set_embedding(entry, vector)

    def missing_vectors(self) -> list[Entry]:
        """The lines that wait for a vector."""
        return [entry for entry in self.entries() if entry.embedding is None]

    def check_model(self, identity: str) -> bool:
        """Clear every vector if another embedding model made them. Returns
        ``True`` if it cleared them."""
        if self._store.embedding_model() == identity:
            return False
        self._store.reset_embeddings(identity)
        return True
