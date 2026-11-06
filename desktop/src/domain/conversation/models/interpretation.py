"""What the AI model found in one message of the user.

The model fills the whole schema. These are the fields that something reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.events.models import MessageClass


@dataclass(frozen=True)
class Interpretation:
    """``importance`` covers the whole message, from 1 to 10. ``event_class`` is
    ``None`` when the model named no class from the closed set. ``confidence``
    is from 0 to 1. ``crisis`` is the model's own reading, apart from the
    tripwire.

    Raises ``ValueError`` for an importance or a confidence outside its range.
    """

    importance: int
    facts: tuple[str, ...]
    event_class: MessageClass | None = None
    confidence: float = 0.0
    crisis: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.importance <= 10:
            raise ValueError(f"importance must be 1 to 10, not {self.importance}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be 0 to 1, not {self.confidence}")
