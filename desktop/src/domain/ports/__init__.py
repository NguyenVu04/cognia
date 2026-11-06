"""Ports: what the domain needs, stated without naming who provides it."""

from src.domain.ports.character_catalog import (
    CharacterCatalog,
    CharacterCatalogUnavailable,
)
from src.domain.ports.character_store import CharacterStore, CharacterStoreFailed
from src.domain.ports.conversation_store import (
    ConversationStore,
    ConversationStoreFailed,
)
from src.domain.ports.dictionary import Dictionary, DictionaryUnavailable, Sense
from src.domain.ports.embedder import Embedder, EmbedFailed
from src.domain.ports.erasure_store import ErasureFailed, ErasureStore
from src.domain.ports.event_log import EventLog, EventLogFailed
from src.domain.ports.interpreter import Interpreter, InterpretFailed
from src.domain.ports.memory_store import MemoryStore, MemoryStoreFailed
from src.domain.ports.presence_source import (
    PresenceFailed,
    PresenceSample,
    PresenceSource,
)
from src.domain.ports.replier import Replier, ReplyFailed

__all__ = [
    "CharacterCatalog",
    "CharacterCatalogUnavailable",
    "CharacterStore",
    "CharacterStoreFailed",
    "ConversationStore",
    "ConversationStoreFailed",
    "Dictionary",
    "DictionaryUnavailable",
    "EmbedFailed",
    "Embedder",
    "ErasureFailed",
    "ErasureStore",
    "EventLog",
    "EventLogFailed",
    "InterpretFailed",
    "Interpreter",
    "MemoryStore",
    "MemoryStoreFailed",
    "PresenceFailed",
    "PresenceSample",
    "PresenceSource",
    "Replier",
    "ReplyFailed",
    "Sense",
]
