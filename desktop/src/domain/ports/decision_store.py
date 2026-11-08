"""The port that keeps each decision to speak and the figures behind it."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from src.domain.speech.models import Factor, MessageKind, Outcome


class DecisionStoreFailed(Exception):
    """A decision could not be read or written. Carries user-facing text."""


class DecisionStore(Protocol):
    """Each method raises :class:`DecisionStoreFailed` if it cannot do its work."""

    def record(
        self,
        kind: MessageKind,
        trigger_seq: int | None,
        decided_at: datetime,
        outcome: Outcome,
        withheld_by: str,
        factors: Sequence[Factor],
    ) -> str:
        """Keep one decision with its figures, in order. Returns its id."""
        ...

    def respond(self, decision_id: str, response: str) -> None:
        """Keep what the user did with a message that was shown."""
        ...

    def sent_since(self, moment: datetime, kinds: Sequence[MessageKind]) -> int:
        """How many messages of these kinds were sent at ``moment`` or later."""
        ...
