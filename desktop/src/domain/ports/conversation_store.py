"""The port through which conversations are kept.

Ports belong to the domain, and adapters implement them. This one
says nothing about SQLite, files or paths — swapping the store is a change in
``infrastructure/`` and nowhere else.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.domain.conversation.models import Conversation, Message, Summary


class ConversationStoreFailed(Exception):
    """A conversation could not be changed, with a sentence saying so.

    Carries user-facing text. A failed change leaves everything as it was.
    """


class ConversationStore(Protocol):
    """Somewhere a conversation and its messages survive a restart."""

    def create(self, now: datetime) -> Conversation:
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

    def summary(self, conversation_id: str) -> Summary | None:
        """The summary of the older messages, or ``None``. Raises
        :class:`ConversationStoreFailed` if it cannot be read."""
        ...

    def set_summary(self, conversation_id: str, summary: Summary) -> bool:
        """Keep ``summary`` if the conversation exists and the summary covers
        more messages than the one kept. Whether it was kept. Raises
        :class:`ConversationStoreFailed` if it cannot be written."""
        ...

    def search(
        self, query: str, limit: int, exclude_message_id: str | None = None
    ) -> list[Message]:
        """The messages that hold every word of ``query``, best match first,
        without the message ``exclude_message_id``. Raises
        :class:`ConversationStoreFailed` if they cannot be read."""
        ...

    def delete(self, conversation_id: str) -> None:
        """Remove a conversation and every message in it. Raises
        :class:`ConversationStoreFailed` if nothing could be removed."""
        ...

    def close(self) -> None:
        """Release whatever the store is holding."""
        ...
