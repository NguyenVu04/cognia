"""Everything that reaches the core thread, as frozen values in one queue.

The GUI sends what the user did; the model thread sends what the model
returned. Frozen, so nothing changes under the one reader.
"""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime

from src.app.chat_worker import Prepared, SummaryDone
from src.domain.awareness.models import PresenceChange
from src.domain.erasure.models import Level
from src.domain.memory.models import MemoryItem, Vector
from src.domain.speech.models import MessageKind, SpeechSettings
from src.domain.tools.models import ToolCall, ToolResult

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
class PreviewConversationDeletion:
    """Count what deleting a conversation would remove, before it goes."""

    conversation_id: str


@dataclass(frozen=True)
class DeleteConversation:
    conversation_id: str


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
class SetAwareness:
    """Switch desk awareness on or off. ``error`` says why it went off, when
    the facts could not be read."""

    on: bool
    error: str = ""


@dataclass(frozen=True)
class PresenceReported:
    """A change the presence sampler saw."""

    change: PresenceChange


@dataclass(frozen=True)
class ActivityEnded:
    """An exercise done together stopped, after ``seconds``."""

    activity: str
    seconds: int


@dataclass(frozen=True)
class RateMessage:
    """The user rated a companion message: 1, -1, or 0 to take it back."""

    message_id: str
    rating: int


@dataclass(frozen=True)
class ExplainFeeling:
    """Show why the companion feels as it does."""


@dataclass(frozen=True)
class StartActivity:
    """The user asked for an exercise from a message, such as "breathing"."""

    activity: str


@dataclass(frozen=True)
class WindowOpened:
    """The main window was shown by the user."""


@dataclass(frozen=True)
class RespondToMessage:
    """What the user did with a message the companion started."""

    decision_id: str
    response: str


@dataclass(frozen=True)
class SetKind:
    """Switch one kind of message on or off, with no question asked."""

    kind: MessageKind
    enabled: bool


@dataclass(frozen=True)
class SaveSpeechSettings:
    settings: SpeechSettings


@dataclass(frozen=True)
class Pause:
    """Pause until ``until``; ``None`` until the user resumes."""

    until: datetime | None


@dataclass(frozen=True)
class Resume:
    pass


@dataclass(frozen=True)
class CompanionShown:
    """The companion was shown on the desktop (``True``) or hidden."""

    shown: bool


@dataclass(frozen=True)
class CompanionMoved:
    x: int
    y: int
    screen: str


@dataclass(frozen=True)
class CloseHintShown:
    pass


@dataclass(frozen=True)
class SetSpeakAloud:
    on: bool


@dataclass(frozen=True)
class SetHotkey:
    sequence: str


@dataclass(frozen=True)
class ExcludeApp:
    name: str


@dataclass(frozen=True)
class IncludeApp:
    name: str


@dataclass(frozen=True)
class AddToolServer:
    name: str
    transport: str
    command: str
    args: tuple[str, ...]
    url: str


@dataclass(frozen=True)
class RemoveToolServer:
    server_id: str


@dataclass(frozen=True)
class UndoLearned:
    learned_id: str


@dataclass(frozen=True)
class MarkLearnedWrong:
    learned_id: str


@dataclass(frozen=True)
class Stop:
    """Close the database and end the core thread."""


# ── from the model thread ──────────────────────────────────────────────────


@dataclass(frozen=True)
class TurnPrepared:
    prepared: Prepared


@dataclass(frozen=True)
class ReplyArrived:
    """The whole reply of turn ``turn_id``, and what each tool gave back."""

    turn_id: int
    text: str
    results: tuple[ToolResult, ...] = ()


@dataclass(frozen=True)
class ToolRequested:
    """A tool in a reply needs the core's data. The core sets ``answer`` to a
    sentence; the model thread waits for it."""

    call: ToolCall
    now: datetime
    answer: Future = field(compare=False)


@dataclass(frozen=True)
class ReplyLost:
    """No reply came for turn ``turn_id``. ``text`` says why, for the user."""

    turn_id: int
    text: str


@dataclass(frozen=True)
class SummaryMade:
    done: SummaryDone


@dataclass(frozen=True)
class VectorsMade:
    pairs: tuple[tuple[MemoryItem, Vector], ...]


@dataclass(frozen=True)
class DeviceChosen:
    name: str


@dataclass(frozen=True)
class Worded:
    """The model worded message ``job_id``; "" when it could not."""

    job_id: int
    text: str


Command = (
    SendMessage
    | OpenConversation
    | NewConversation
    | PreviewConversationDeletion
    | DeleteConversation
    | OfferCharacters
    | ChooseCharacter
    | RestoreVersion
    | CorrectEntry
    | RemoveEntry
    | PreviewErasure
    | Erase
    | ActivityEnded
    | SetAwareness
    | PresenceReported
    | Stop
    | TurnPrepared
    | ReplyArrived
    | ReplyLost
    | SummaryMade
    | ToolRequested
    | VectorsMade
    | DeviceChosen
    | Worded
    | RateMessage
    | ExplainFeeling
    | StartActivity
    | WindowOpened
    | RespondToMessage
    | SetKind
    | SaveSpeechSettings
    | Pause
    | Resume
    | CompanionShown
    | CompanionMoved
    | CloseHintShown
    | SetSpeakAloud
    | SetHotkey
    | ExcludeApp
    | IncludeApp
    | AddToolServer
    | RemoveToolServer
    | UndoLearned
    | MarkLearnedWrong
)
