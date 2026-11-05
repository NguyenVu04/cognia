"""One thing the companion remembers about the user, other than a commitment.

``text`` is the exact line the user was shown. A ``told`` item is something the
user said about themselves; a ``noticed`` item is a conclusion of the companion
and always carries its reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

TOLD = "told"
NOTICED = "noticed"


@dataclass(frozen=True)
class MemoryItem:
    """Raises ``ValueError`` for a value the stored row would refuse.

    ``embedding`` is ``None`` until its vector is computed, and again after an
    edit.
    """

    id: str
    kind: str
    text: str
    reason: str | None
    source_message_id: str | None
    importance: int | None
    last_retrieved_at: datetime | None
    recorded_at: datetime
    embedding: tuple[float, ...] | None

    def __post_init__(self) -> None:
        if self.kind not in (TOLD, NOTICED):
            raise ValueError(f"kind must be told or noticed, not {self.kind!r}")
        if not self.text.strip():
            raise ValueError("A remembered item needs words.")
        if self.kind == NOTICED and not (self.reason or "").strip():
            raise ValueError("A noticed item needs its reason.")
        check_importance(self.importance)


def check_importance(importance: int | None) -> None:
    if importance is not None and not 1 <= importance <= 10:
        raise ValueError(f"importance must be 1 to 10, not {importance}")
