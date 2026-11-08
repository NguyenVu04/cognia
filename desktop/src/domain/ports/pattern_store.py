"""The port that keeps the patterns the companion learned, with their evidence
and what each one changed."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from src.domain.learning.models import Adjustment, Learned, Pattern


class PatternStoreFailed(Exception):
    """A pattern could not be read or written. Carries user-facing text."""


class PatternStore(Protocol):
    """Each method raises :class:`PatternStoreFailed` if it cannot do its work."""

    def add(
        self, pattern: Pattern, adjustments: Sequence[Adjustment], at: datetime
    ) -> Learned:
        ...

    def all(self) -> list[Learned]:
        """Every pattern, newest first, undone ones included."""
        ...

    def undo(self, learned_id: str, at: datetime) -> Learned | None:
        """Mark the changes of a pattern undone. ``None`` if there is none."""
        ...

    def remove(self, learned_id: str) -> Learned | None:
        """Delete a pattern, its evidence and its changes. Returns what it was."""
        ...
