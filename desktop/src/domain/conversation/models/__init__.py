"""Domain models. The standard library only — no Qt, no adapters, no I/O."""

from src.domain.conversation.models.conversation import Conversation
from src.domain.conversation.models.message import COMPANION, USER, Message

__all__ = ["COMPANION", "Conversation", "Message", "USER"]
