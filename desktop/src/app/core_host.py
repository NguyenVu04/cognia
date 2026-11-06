"""The core thread: the one reader of the one queue, and the one connection.

Everything that reads or writes data happens here, one command at a time and
in the order the commands arrived, so a slow write never stops the window from
drawing. The GUI sends commands through the :class:`Bridge` and receives finished
data as its signals. Effects leave only after the data they show is committed.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.app.bridge import Bridge
from src.app.chat_worker import Prepared, TurnRequest
from src.app.commands import (
    ChooseCharacter,
    Command,
    CorrectEntry,
    DeviceChosen,
    Erase,
    NewConversation,
    OfferCharacters,
    OpenConversation,
    PreviewErasure,
    RemoveEntry,
    ReplyArrived,
    ReplyLost,
    RestoreVersion,
    SendMessage,
    Stop,
    TurnPrepared,
    VectorsMade,
)
from src.domain.character import rules as character_rules
from src.domain.character.character_service import CharacterService
from src.domain.companion import rules as companion_rules
from src.domain.companion.companion_service import CompanionService
from src.domain.conversation import rules
from src.domain.conversation.models import COMPANION, USER, Message
from src.domain.emotion.emotion_service import EmotionService
from src.domain.erasure.erasure_service import ErasureService
from src.domain.erasure.models import Level
from src.domain.events.models import EventKind, Payload
from src.domain.memory import rules as memory_rules
from src.domain.memory.memory_service import MemoryService
from src.domain.memory.models import (
    Calibration,
    Commitment,
    Entry,
    MemoryItem,
    Scored,
    Selection,
    Vector,
)
from src.domain.ports import (
    CharacterCatalogUnavailable,
    CharacterStoreFailed,
    ErasureFailed,
    EventLogFailed,
    MemoryStoreFailed,
)
from src.domain.safety import rules as safety_rules
from src.infrastructure.storage.character_catalog import TomlCharacterCatalog
from src.infrastructure.storage.character_store import SqliteCharacterStore
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.erasure_store import SqliteErasureStore
from src.infrastructure.storage.event_log import SqliteEventLog
from src.infrastructure.storage.memory_store import SqliteMemoryStore
from src.infrastructure.storage.settings_store import SqliteSettings
from src.infrastructure.storage.sqlite_store import (
    UNTITLED,
    SqliteConversationStore,
    title_from,
)
from src.utils import paths

NOT_SAVED = "The reply could not be saved, so nothing from it was kept. Try again."
STEP_FAILED = "Something went wrong, and nothing from that step was saved. Try again."
NOT_OPENED = (
    "Cognia could not open its data file, so nothing can be shown or saved. "
    "Restarting Cognia may help."
)


@dataclass(frozen=True)
class _Turn:
    """One message of the user on its way to a reply."""

    id: int
    conversation_id: str
    message_id: str
    history: tuple[Message, ...]


@dataclass(frozen=True)
class _Ready:
    """What the reply of a turn will store once it arrives."""

    selection: Selection | None
    importance: int
    vectors: Mapping[str, Vector]
    recalled: tuple[Scored, ...]
    lines: tuple[str, ...]


def _offset(moment: datetime) -> int:
    return int(moment.utcoffset().total_seconds() // 60)


def _now() -> datetime:
    return datetime.now().astimezone()


class CoreHost(threading.Thread):
    """Holds the database, the services and the companion's state.

    ``embedding_identity`` names the embedding model file, or ``None`` if it is
    missing. ``device_loaded`` receives the stored GPU name, or ``None``, on this
    thread at start, before any model request. A command that fails in a way
    nobody expected is reported through ``Bridge.coreFailed`` with the command
    itself, so the window can say so where the user asked for it, and the next
    command is handled as usual.
    """

    def __init__(
        self,
        database_path: Path,
        bridge: Bridge,
        *,
        calibration: Calibration,
        history_messages: int,
        embedding_identity: str | None,
        device_loaded: Callable[[str | None], None],
    ) -> None:
        super().__init__(name="cognia-core", daemon=True)
        self._database_path = database_path
        self._bridge = bridge
        self._calibration = calibration
        self._history_messages = history_messages
        self._embedding_identity = embedding_identity
        self._device_loaded = device_loaded
        self._db: Database | None = None
        self._version = None
        self._prompt = ""
        self._turn_count = 0
        self._turn: _Turn | None = None
        self._ready: _Ready | None = None

    # ── the loop ──────────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self._open()
            self._show_everything()
        except Exception:  # noqa: BLE001 - the window must learn why it is empty
            self._bridge.coreFailed.emit(NOT_OPENED, None)
        self._bridge.ready.emit()
        while True:
            item = self._bridge.commands.get()
            if isinstance(item, Stop):
                break
            try:
                self._handle(item)
            except Exception:  # noqa: BLE001 - one broken step must not end the core
                self._bridge.coreFailed.emit(STEP_FAILED, item)
        if self._db is not None:
            self._db.close()

    def _handle(self, item: Command) -> None:
        match item:
            case SendMessage(text):
                self._send(text)
            case TurnPrepared(prepared):
                self._prepared(prepared)
            case ReplyArrived(text):
                self._replied(text)
            case ReplyLost(text):
                self._turn = self._ready = None
                self._bridge.replyFailed.emit(text)
            case NewConversation():
                self._new_conversation()
            case OpenConversation(conversation_id):
                self._open_conversation(conversation_id)
            case OfferCharacters():
                version = self._version
                self._show_templates(version.template_id if version else None)
            case ChooseCharacter(template_id):
                self._choose(template_id)
            case RestoreVersion(version_id):
                self._put_in_force(
                    lambda now: self._characters.restore(version_id, now)
                )
            case CorrectEntry(entry, text):
                self._correct(entry, text)
            case RemoveEntry(entry):
                self._remove(entry)
            case VectorsMade(pairs):
                self._embedded(pairs)
            case PreviewErasure(level):
                self._preview(level)
            case Erase(level):
                self._erase(level)
            case DeviceChosen(name):
                self._settings.set_chat_device(name)

    def _open(self) -> None:
        """Open the database on this thread: its one connection lives here."""
        db = self._db = Database.open(self._database_path)
        self._store = SqliteConversationStore(db)
        character_store = SqliteCharacterStore(db)
        self._characters = CharacterService(
            character_store, TomlCharacterCatalog(paths.resource("characters.toml"))
        )
        self._memory = MemoryService(SqliteMemoryStore(db))
        self._erasure = ErasureService(SqliteErasureStore(db))
        self._settings = SqliteSettings(db)
        self._companion = CompanionService(
            SqliteEventLog(db), EmotionService(character_store)
        )
        self._state = self._fold()
        self._conversation = self._store.latest() or self._store.create(_now())
        self._device_loaded(self._settings.chat_device())

    def _show_everything(self) -> None:
        self._load_character()
        self._bridge.conversationLoaded.emit(self._store.history(self._conversation.id))
        self._refresh_picker()
        self._refresh_memory()
        if self._embedding_identity is not None:
            try:
                self._memory.check_model(self._embedding_identity)
            except MemoryStoreFailed:
                pass
        self._embed_missing()
        if self._version is None:
            self._show_templates(None)

    # ── the conversation ──────────────────────────────────────────────────

    def _send(self, text: str) -> None:
        """The user has said something. Record it, show it, then prepare."""
        if self._version is None:
            self._show_templates(None)
            return
        now = _now()
        conversation = self._conversation
        message = self._store.append(Message.new(conversation.id, USER, text, now))
        if conversation.title == UNTITLED:
            self._store.retitle(conversation.id, title_from(text))
            self._conversation = self._reread(conversation.id)

        self._bridge.messageAppended.emit(message)
        self._refresh_picker()

        history = tuple(self._store.history(conversation.id, self._history_messages))
        self._turn_count += 1
        self._turn = _Turn(self._turn_count, conversation.id, message.id, history)
        self._ready = None
        self._bridge.askPrepare.emit(
            TurnRequest(
                turn_id=self._turn.id,
                system_prompt=self._prompt,
                history=history,
                entries=tuple(self._entries()),
                crisis=safety_rules.tripwire(text),
                today=now.date(),
                now=now,
                calibration=self._calibration,
            )
        )

    def _prepared(self, prepared: Prepared) -> None:
        """Choose what to keep, and ask for the reply with what it draws on."""
        turn = self._turn
        if turn is None or prepared.turn_id != turn.id:
            return  # a turn that was abandoned
        selection, lines, importance = None, (), 1
        if prepared.found is not None:
            importance = prepared.found.importance
            selection = memory_rules.select(
                prepared.found, self._entries(), prepared.vectors, self._calibration
            )
            lines = (*selection.facts, *(c.text for c in selection.commitments))
        self._ready = _Ready(
            selection, importance, prepared.vectors, prepared.recalled, lines
        )
        zone = _now().tzinfo
        remembered = [
            memory_rules.recalled_line(s.entry, zone) for s in prepared.recalled
        ]
        turn_text = rules.turn_text("", remembered, rules.show_back_instruction(lines))
        self._bridge.askReply.emit(self._prompt, list(turn.history), turn_text)

    def _replied(self, text: str) -> None:
        """A reply arrived whole. It, and everything the turn keeps, is recorded
        only now and in one transaction, never mid-stream."""
        turn, ready = self._turn, self._ready
        self._turn = self._ready = None
        now = _now()
        note = ""
        if ready is not None and ready.lines:
            missing = [
                line for line in ready.lines if not memory_rules.shows_back(text, line)
            ]
            note = memory_rules.stored_note(missing, now.date())
        conversation_id = turn.conversation_id if turn else self._conversation.id
        try:
            with self._db.transaction():
                reply = self._store.append(
                    Message.new(conversation_id, COMPANION, text, now)
                )
                state = self._state
                if turn is not None and ready is not None:
                    state = self._keep(turn, ready, reply, now, state)
        except (MemoryStoreFailed, EventLogFailed) as error:
            self._bridge.replyNotSaved.emit(text, str(error) or NOT_SAVED)
            return
        self._state = state
        self._bridge.replyFinished.emit(text, note)
        self._refresh_picker()
        self._refresh_memory()
        self._embed_missing()

    def _keep(self, turn: _Turn, ready: _Ready, reply: Message, now: datetime, state):
        """Store the chosen lines with their events, and link what the reply drew
        on. Runs inside the caller's transaction."""
        if ready.selection is not None:
            stored = self._memory.remember(
                ready.selection, ready.importance, turn.message_id, ready.vectors, now
            )
            for entry in stored:
                if isinstance(entry, MemoryItem):
                    kind = EventKind.MEMORY_STORED
                    payload = {"memory_item_id": entry.id}
                else:
                    kind = EventKind.COMMITMENT_ADDED
                    payload = {"commitment_id": entry.id}
                state = self._record(state, now, kind, payload)
        self._memory.use(reply.id, [s.entry for s in ready.recalled], now)
        return state

    def _new_conversation(self) -> None:
        if not self._store.history(self._conversation.id, 1):
            return  # already sitting in an empty one; don't pile up more
        self._conversation = self._store.create(_now())
        self._bridge.conversationLoaded.emit([])
        self._refresh_picker()

    def _open_conversation(self, conversation_id: str) -> None:
        if conversation_id == self._conversation.id:
            return
        self._conversation = self._reread(conversation_id)
        self._bridge.conversationLoaded.emit(self._store.history(conversation_id))
        self._refresh_picker()

    def _reread(self, conversation_id: str):
        found = next(
            (c for c in self._store.conversations() if c.id == conversation_id), None
        )
        return found or self._conversation

    def _refresh_picker(self) -> None:
        self._bridge.conversationsChanged.emit(
            self._store.conversations(), self._conversation.id
        )

    # ── memory ────────────────────────────────────────────────────────────

    def _entries(self) -> list[Entry]:
        try:
            return self._memory.entries()
        except MemoryStoreFailed:
            return []

    def _refresh_memory(self) -> None:
        try:
            entries = self._memory.entries()
        except MemoryStoreFailed as error:
            self._bridge.memoryFailed.emit(str(error))
            return
        self._bridge.memoryShown.emit(
            [e for e in entries if isinstance(e, MemoryItem)],
            [e for e in entries if isinstance(e, Commitment)],
        )

    def _correct(self, entry: Entry, text: str) -> None:
        try:
            self._memory.correct(entry, text)
        except ValueError:
            pass  # the view refuses a blank line before it gets here
        except MemoryStoreFailed as error:
            self._bridge.memoryFailed.emit(str(error))
            return
        self._refresh_memory()
        self._embed_missing()

    def _remove(self, entry: Entry) -> None:
        now = _now()
        if isinstance(entry, MemoryItem):
            kind, payload = EventKind.MEMORY_REMOVED, {"memory_item_id": entry.id}
        else:
            kind = EventKind.COMMITMENT_CLOSED
            payload = {"commitment_id": entry.id, "finished": False}
        try:
            with self._db.transaction():
                self._memory.remove(entry)
                state = self._record(self._state, now, kind, payload)
        except (MemoryStoreFailed, EventLogFailed) as error:
            self._bridge.memoryFailed.emit(str(error))
            return
        self._state = state
        self._refresh_memory()

    def _embed_missing(self) -> None:
        try:
            missing = self._memory.missing_vectors()
        except MemoryStoreFailed:
            return
        if missing:
            self._bridge.askEmbed.emit(missing)

    def _embedded(self, pairs) -> None:
        for entry, vector in pairs:
            try:
                self._memory.store_vector(entry, vector)
            except MemoryStoreFailed:
                return  # it waits for the next chance

    # ── character ─────────────────────────────────────────────────────────

    def _load_character(self) -> None:
        """Put the version in force everywhere it shows."""
        try:
            self._version = self._characters.current()
        except CharacterStoreFailed:
            self._version = None
        version = self._version
        if version is None:
            self._prompt = ""
            self._bridge.characterShown.emit(None, [], None, "")
            return
        self._prompt = (
            f"{rules.system_text(version.description)}\n\n{rules.REASONING_RULE}"
        )
        try:
            history = self._characters.history()
        except CharacterStoreFailed as error:
            self._bridge.characterShown.emit(version, [], None, str(error))
            return
        first = min(history, key=lambda v: v.number)
        earlier = [
            (v, character_rules.in_force_until(v, history))
            for v in history
            if v.id != version.id
        ]
        self._bridge.characterShown.emit(
            version, earlier, first.created_at.astimezone().date(), ""
        )

    def _show_templates(self, in_force: str | None) -> None:
        try:
            templates = self._characters.templates()
        except CharacterCatalogUnavailable as error:
            self._bridge.templatesShown.emit([], in_force, str(error))
            return
        self._bridge.templatesShown.emit(templates, in_force, "")

    def _choose(self, template_id: str) -> None:
        first = self._version is None
        self._put_in_force(lambda now: self._characters.choose(template_id, now))
        if self._version is not None:
            self._bridge.screenRequested.emit("chat" if first else "character")

    def _put_in_force(self, add) -> None:
        """Add a version and record ``character_changed`` in one transaction."""
        now = _now()
        try:
            with self._db.transaction():
                version = add(now)
                state = self._record(
                    self._state, now, EventKind.CHARACTER_CHANGED,
                    {"version_id": version.id},
                )
        except (CharacterStoreFailed, EventLogFailed, ValueError) as error:
            self._bridge.characterFailed.emit(str(error))
            return
        self._state = state
        self._load_character()

    # ── erasure ───────────────────────────────────────────────────────────

    def _preview(self, level: Level) -> None:
        try:
            counts = self._erasure.preview(level)
        except ErasureFailed as error:
            self._bridge.memoryFailed.emit(str(error))
            return
        name = self._version.name if self._version else None
        self._bridge.erasurePreviewed.emit(level, counts, name)

    def _erase(self, level: Level) -> None:
        # Nothing from a turn in flight may be kept after the erasure.
        self._turn = self._ready = None
        report = self._erasure.erase(level)
        self._bridge.erasureReported.emit(report)
        self._after_erasure()

    def _after_erasure(self) -> None:
        """Show what is left. The feelings start again at the resting mood of the
        character that remains, if one does."""
        self._state = self._fold()
        self._load_character()
        if self._version is not None:
            now = _now()
            try:
                with self._db.transaction():
                    state = self._record(
                        self._state, now, EventKind.CHARACTER_CHANGED,
                        {"version_id": self._version.id},
                    )
                self._state = state
            except EventLogFailed:
                pass
        self._conversation = self._store.latest() or self._store.create(_now())
        self._bridge.conversationLoaded.emit(self._store.history(self._conversation.id))
        self._refresh_picker()
        self._refresh_memory()

    # ── events ────────────────────────────────────────────────────────────

    def _record(self, state, now: datetime, kind: EventKind, payload: Payload):
        return self._companion.record(
            state, now, _offset(now), kind, payload, None
        ).state

    def _fold(self):
        try:
            return self._companion.start()
        except (EventLogFailed, ValueError):
            return companion_rules.initial_state()
