"""Ports: what the domain needs, stated without naming who provides it."""

from src.domain.ports.character_catalog import (
    CharacterCatalog,
    CharacterCatalogUnavailable,
)
from src.domain.ports.character_store import CharacterStore, CharacterStoreFailed
from src.domain.ports.conversation_store import ConversationStore
from src.domain.ports.event_log import EventLog, EventLogFailed
from src.domain.ports.replier import Replier, ReplyFailed

__all__ = [
    "CharacterCatalog",
    "CharacterCatalogUnavailable",
    "CharacterStore",
    "CharacterStoreFailed",
    "ConversationStore",
    "EventLog",
    "EventLogFailed",
    "Replier",
    "ReplyFailed",
]
