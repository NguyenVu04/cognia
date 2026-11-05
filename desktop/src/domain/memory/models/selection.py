"""The values that retrieval and selection pass around."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.conversation.models import SaidCommitment
from src.domain.memory.models.commitment import Commitment
from src.domain.memory.models.memory_item import MemoryItem

Entry = MemoryItem | Commitment
Vector = tuple[float, ...]


@dataclass(frozen=True)
class Scored:
    entry: Entry
    score: float


@dataclass(frozen=True)
class Selection:
    """The new lines worth keeping from one message, after the rules."""

    facts: tuple[str, ...]
    commitments: tuple[SaidCommitment, ...]


@dataclass(frozen=True)
class Calibration:
    """Figures that belong to the embedding model, so they change with it.

    ``baseline`` is the cosine that two unrelated lines still reach.
    ``near_duplicate`` is the cosine at or above which a new line is the same as
    a stored one. Raises ``ValueError`` outside 0 to 1.
    """

    baseline: float
    near_duplicate: float

    def __post_init__(self) -> None:
        if not 0 <= self.baseline < 1:
            raise ValueError(f"baseline must be 0 to below 1, not {self.baseline}")
        if not 0 < self.near_duplicate <= 1:
            raise ValueError(
                f"near_duplicate must be above 0 to 1, not {self.near_duplicate}"
            )
