"""A conversation: the thread a character and the user share.

Pure data. The domain holds no clock of its own — ``started_at`` and
``last_active_at`` are handed in by whoever creates the record, so a replay
over recorded input produces the same values it did the first time (NFR-14).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Conversation:
    id: str
    character_id: str
    title: str
    started_at: datetime
    last_active_at: datetime
