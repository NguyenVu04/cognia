"""Everything that reaches the core thread, as frozen values in one queue.

The GUI sends what the user did; the model thread sends what the model
returned. Frozen, so nothing changes under the one reader.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.app.chat_worker import Prepared
from src.domain.erasure.models import Level
from src.domain.memory.models import MemoryItem, Vector

# ── from the GUI ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SendMessage:
    text: str


@dataclass(frozen=True)
class OpenConversation:
    conversation_id: str


@dataclass(frozen=True)
class NewConversation:
    pass


@dataclass(frozen=True)
class OfferCharacters:
    """Show the ready-made characters, to change the one in force."""


@dataclass(frozen=True)
class ChooseCharacter:
    template_id: str


@dataclass(frozen=True)
class RestoreVersion:
    version_id: str


@dataclass(frozen=True)
class CorrectEntry:
    entry: MemoryItem
    text: str


@dataclass(frozen=True)
class RemoveEntry:
    entry: MemoryItem


@dataclass(frozen=True)
class PreviewErasure:
    level: Level


@dataclass(frozen=True)
class Erase:
    level: Level


@dataclass(frozen=True)
class Stop:
    """Close the database and end the core thread."""


# ── from the model thread ──────────────────────────────────────────────────


@dataclass(frozen=True)
class TurnPrepared:
    prepared: Prepared


@dataclass(frozen=True)
class ReplyArrived:
    text: str


@dataclass(frozen=True)
class ReplyLost:
    """No reply came. ``text`` says why, for the user."""

    text: str


@dataclass(frozen=True)
class VectorsMade:
    pairs: tuple[tuple[MemoryItem, Vector], ...]


@dataclass(frozen=True)
class DeviceChosen:
    name: str


Command = (
    SendMessage
    | OpenConversation
    | NewConversation
    | OfferCharacters
    | ChooseCharacter
    | RestoreVersion
    | CorrectEntry
    | RemoveEntry
    | PreviewErasure
    | Erase
    | Stop
    | TurnPrepared
    | ReplyArrived
    | ReplyLost
    | VectorsMade
    | DeviceChosen
)
