"""The port through which remembered lines are kept."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from src.domain.memory.models import MemoryItem, Vector


class MemoryStoreFailed(Exception):
    """The memory could not be read or changed, with a sentence saying so.

    Carries user-facing text. A list that cannot be read is never shown as
    complete, and a failed change leaves the memory as it was.
    """


class MemoryStore(Protocol):
    """Every remembered line, with its vector.

    Each method raises :class:`MemoryStoreFailed` if it cannot do its work.
    """

    def items(self) -> list[MemoryItem]:
        """Every remembered line, newest first."""
        ...

    def add(self, entry: MemoryItem) -> None: ...

    def correct(self, entry: MemoryItem, text: str) -> None:
        """Replace the words and drop the vector, which no longer fits them."""
        ...

    def remove(self, entry: MemoryItem) -> None:
        """Delete it, with its vector and its links to replies."""
        ...

    def set_embedding(self, entry: MemoryItem, vector: Vector) -> None: ...

    def link(
        self, message_id: str, entries: Sequence[MemoryItem], now: datetime
    ) -> None:
        """Record that the reply drew on ``entries``, and that they were used
        at ``now``."""
        ...

    def embedding_model(self) -> str | None:
        """The model that made the stored vectors, or ``None`` if not recorded."""
        ...

    def reset_embeddings(self, model: str) -> None:
        """Drop every stored vector and record ``model`` as the one in use."""
        ...

    def close(self) -> None:
        """Release whatever the store is holding."""
        ...
