"""One line of a conversation.

``role`` is the design's own one-letter convention — ``"u"`` for the user and
``"c"`` for the companion — so the bubbles keep reading it the way they always
have. ``note`` is the "Stored — you told me" chip the design shows underneath a
companion message; nothing writes it yet.
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
