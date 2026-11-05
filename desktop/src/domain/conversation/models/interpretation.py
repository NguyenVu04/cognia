"""What the AI model found in one message of the user that is worth keeping.

The model fills the whole schema that the tuned model learns. These are the
fields that something reads today.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SaidCommitment:
    """Something the user said they have to do, with the day if they gave one.

    Raises ``ValueError`` for blank text.
    """

    text: str
    due_on: date | None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("A commitment needs words.")


@dataclass(frozen=True)
class Interpretation:
    """``importance`` covers the whole message, from 1 to 10.

    Raises ``ValueError`` for an importance outside that range.
    """

    importance: int
    facts: tuple[str, ...]
    commitments: tuple[SaidCommitment, ...]

    def __post_init__(self) -> None:
        if not 1 <= self.importance <= 10:
            raise ValueError(f"importance must be 1 to 10, not {self.importance}")
