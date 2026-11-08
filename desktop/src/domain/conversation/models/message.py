"""One line of a conversation.

``role`` is ``"u"`` for the user and ``"c"`` for the companion. ``note`` is the
chip under a companion message that says what was stored; it is not kept, so a
message read back from the store has none. ``rating`` is the user's thumbs up
(1) or down (-1) on a companion message, or ``None``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

USER = "u"
COMPANION = "c"


@dataclass(frozen=True)
class Message:
    id: str
    conversation_id: str
    role: str
    text: str
    created_at: datetime
    note: str = ""
    rating: int | None = None

    @property
    def from_user(self) -> bool:
        return self.role == USER

    @classmethod
    def new(
        cls,
        conversation_id: str,
        role: str,
        text: str,
        created_at: datetime,
        note: str = "",
    ) -> "Message":
        """A message that has not been stored yet. The clock is handed in."""
        return cls(uuid.uuid4().hex, conversation_id, role, text, created_at, note)
