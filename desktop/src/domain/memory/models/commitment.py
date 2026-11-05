"""Something the user said they have to do.

It has no time of day and no status: Cognia keeps no task list and sets no
alarm. When the user says it is done or no longer wanted, the row goes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from src.domain.memory.models.memory_item import check_importance


@dataclass(frozen=True)
class Commitment:
    """Raises ``ValueError`` for a value the stored row would refuse."""

    id: str
    text: str
    due_on: date | None
    source_message_id: str | None
    importance: int | None
    last_retrieved_at: datetime | None
    recorded_at: datetime
    embedding: tuple[float, ...] | None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("A commitment needs words.")
        check_importance(self.importance)
