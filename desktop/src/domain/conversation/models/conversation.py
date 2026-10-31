"""A conversation: the thread a character and the user share.

Pure data. The domain holds no clock of its own — ``last_active_at`` is handed
in by whoever creates the record, so a replay over recorded input produces the
same value it did the first time (NFR-13).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    last_active_at: datetime
