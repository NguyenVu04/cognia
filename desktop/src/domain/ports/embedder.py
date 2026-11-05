"""The port that turns text into vectors."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EmbedFailed(Exception):
    """No vectors could be made, with a sentence saying why."""


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        """One vector for each text, in the same order. A text longer than the
        model accepts is cut first. Raises :class:`EmbedFailed`."""
        ...
