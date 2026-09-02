"""The port through which conversations are kept.

ADR 0001: ports belong to the domain, and adapters implement them. This one
says nothing about SQLite, files or paths — swapping the store is a change in
``infrastructure/`` and nowhere else.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.core.models import Conversation, Message


class ConversationStore(Protocol):
    """Somewhere a conversation and its messages survive a restart."""

    def create(self, character_id: str, now: datetime) -> Conversation:
        """Open a new, empty conversation and return it."""
        ...

    def conversations(self) -> list[Conversation]:
        """Every conversation, most recently active first."""
        ...

    def latest(self) -> Conversation | None:
        """The most recently active conversation, or ``None`` if there are none."""
        ...

    def append(self, message: Message) -> Message:
        """Record one message and stamp its conversation as active."""
        ...

    def history(self, conversation_id: str, limit: int | None = None) -> list[Message]:
        """The conversation in order. ``limit`` keeps the *last* n messages."""
        ...

    def retitle(self, conversation_id: str, title: str) -> None:
        """Give a conversation the name the picker shows."""
        ...

    def close(self) -> None:
        """Release whatever the store is holding."""
        ...
