"""Domain models. The standard library only — no Qt, no adapters, no I/O."""

from src.core.models.conversation import Conversation
from src.core.models.message import COMPANION, USER, Message

__all__ = ["COMPANION", "Conversation", "Message", "USER"]
