"""The core thread: the one reader of the one queue, and the one connection.

Everything that reads or writes data happens here, one command at a time and
in the order the commands arrived, so a slow write never stops the window from
drawing. The GUI sends commands through the :class:`Bridge` and receives finished
data as its signals. Effects leave only after the data they show is committed.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from src.app.bridge import Bridge
from src.app.chat_worker import (
    Prepared,
    ReplyRequest,
    SummaryDone,
    SummaryJob,
    TurnRequest,
)
from src.app.commands import (
    ActivityEnded,
    ChooseCharacter,
    Command,
    CorrectEntry,
    DeleteConversation,
    DeviceChosen,
    Erase,
    NewConversation,
    OfferCharacters,
    OpenConversation,
    PresenceReported,
    PreviewConversationDeletion,
    PreviewErasure,
    RemoveEntry,
    ReplyArrived,
    ReplyLost,
    RestoreVersion,
    SendMessage,
    SetAwareness,
    Stop,
    SummaryMade,
    ToolRequested,
    TurnPrepared,
    VectorsMade,
)
from src.domain.awareness import rules as awareness_rules
from src.domain.awareness.awareness_service import AwarenessService
from src.domain.awareness.models import PresenceChange
from src.domain.character import rules as character_rules
from src.domain.character.character_service import CharacterService
from src.domain.companion import rules as companion_rules
from src.domain.companion.companion_service import CompanionService
from src.domain.companion.models import (
    Effect,
    ShowExpression,
    ShowGesture,
    StepResult,
)
from src.domain.conversation import rules
from src.domain.conversation.models import (
    COMPANION,
    USER,
    Interpretation,
    Message,
    Summary,
)
from src.domain.emotion import rules as emotion_rules
from src.domain.emotion.emotion_service import EmotionService
from src.domain.erasure.erasure_service import ErasureService
from src.domain.erasure.models import Level
from src.domain.events.models import EventKind, Payload
from src.domain.memory import rules as memory_rules
from src.domain.memory.memory_service import MemoryService
from src.domain.memory.models import Calibration, MemoryItem, Scored, Vector
from src.domain.ports import (
    CharacterCatalogUnavailable,
    CharacterStoreFailed,
    ConversationStoreFailed,
    ErasureFailed,
    EventLogFailed,
    MemoryStoreFailed,
)
from src.domain.safety import rules as safety_rules
from src.domain.tools import catalog
from src.domain.tools import rules as tool_rules
from src.domain.tools.models import ToolResult
from src.infrastructure.storage.app_usage_store import SqliteAppUsage
from src.infrastructure.storage.character_catalog import TomlCharacterCatalog
from src.infrastructure.storage.character_store import SqliteCharacterStore
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.erasure_store import SqliteErasureStore
from src.infrastructure.storage.event_log import SqliteEventLog
from src.infrastructure.storage.memory_store import SqliteMemoryStore
from src.infrastructure.storage.settings_store import SettingNotSaved, SqliteSettings
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
    tripwire: bool
    system: str = ""


@dataclass(frozen=True)
class _Ready:
    """What the reply of a turn will store once it arrives."""

    importance: int
    vectors: Mapping[str, Vector]
    recalled: tuple[Scored, ...]
    lines: tuple[str, ...]
    crisis: bool
    turn_text: str = ""


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
        history_max_chars: int,
        embedding_identity: str | None,
        device_loaded: Callable[[str | None], None],
    ) -> None:
        super().__init__(name="cognia-core", daemon=True)
        self._database_path = database_path
        self._bridge = bridge
        self._calibration = calibration
        self._history_max_chars = history_max_chars
        self._embedding_identity = embedding_identity
        self._device_loaded = device_loaded
        self._db: Database | None = None
        self._version = None
        self._prompt = ""
        self._turn_count = 0
        self._turn: _Turn | None = None
        self._ready: _Ready | None = None
        self._activity: str | None = None
        self._awareness_on = False

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
            case SummaryMade(done):
                self._summarized(done)
            case ReplyArrived(turn_id, text, results) if self._is_current(turn_id):
                self._replied(text, results)
            case ToolRequested() as request:
                self._answer_tool(request)
            case ActivityEnded(activity, seconds):
                self._activity_ended(activity, seconds)
            case SetAwareness(on, error):
                self._set_awareness(on, error)
            case PresenceReported(change):
                self._presence(change)
            case ReplyLost(turn_id, text) if self._is_current(turn_id):
                self._reply_lost(text)
            case NewConversation() if self._idle():
                self._new_conversation()
            case OpenConversation(conversation_id) if self._idle():
                self._open_conversation(conversation_id)
            case PreviewConversationDeletion(conversation_id) if self._idle():
                self._preview_deletion(conversation_id)
            case DeleteConversation(conversation_id) if self._idle():
                self._delete_conversation(conversation_id)
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
        log = SqliteEventLog(db)
        self._companion = CompanionService(log, EmotionService(character_store))
        self._awareness = AwarenessService(log)
        self._app_usage = SqliteAppUsage(db)
        self._awareness_on = self._settings.awareness_on()
        self._state = self._fold()
        self._conversation = self._store.latest() or self._store.create(_now())
        self._device_loaded(self._settings.chat_device())

    def _show_everything(self) -> None:
        self._load_character()
        self._show_face()
        self._bridge.awarenessChanged.emit(self._awareness_on, "")
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

        self._turn_count += 1
        turn = _Turn(
            self._turn_count, conversation.id, message.id, (),
            safety_rules.tripwire(text),
        )
        self._turn, self._ready = turn, None
        summary = self._summary(conversation.id)
        kept = self._after_summary(conversation.id, summary)
        budget = self._history_max_chars
        if rules.history_chars(kept) > budget:
            fold = rules.fold_point(kept, budget)
            if fold > 0:
                # The turn waits under the working indicator for the summary.
                self._ask_summary(conversation.id, summary, kept, fold, turn.id)
                return
            kept = list(rules.newest_within(kept, budget))
        self._prepare_turn(turn, summary, kept)

    def _prepare_turn(
        self, turn: _Turn, summary: Summary | None, history: Sequence[Message]
    ) -> None:
        """Ask the model thread to prepare ``turn`` with what the model sees."""
        now = _now()
        turn = replace(
            turn,
            history=tuple(history),
            system=rules.with_summary(self._prompt, summary),
        )
        self._turn = turn
        self._bridge.askPrepare.emit(
            TurnRequest(
                turn_id=turn.id,
                system_prompt=turn.system,
                history=turn.history,
                entries=tuple(self._entries()),
                crisis=turn.tripwire,
                today=now.date(),
                now=now,
                calibration=self._calibration,
            )
        )

    def _summary(self, conversation_id: str) -> Summary | None:
        try:
            return self._store.summary(conversation_id)
        except ConversationStoreFailed:
            return None  # the history is then cut instead

    def _after_summary(
        self, conversation_id: str, summary: Summary | None
    ) -> list[Message]:
        """The messages that the summary does not cover."""
        messages = self._store.history(conversation_id)
        return messages[summary.covers:] if summary else messages

    def _ask_summary(
        self,
        conversation_id: str,
        summary: Summary | None,
        kept: Sequence[Message],
        fold: int,
        turn_id: int | None,
    ) -> None:
        covers = (summary.covers if summary else 0) + fold
        self._bridge.askSummary.emit(
            SummaryJob(
                conversation_id,
                summary.text if summary else None,
                tuple(kept[:fold]),
                covers,
                turn_id,
            )
        )

    def _summarized(self, done: SummaryDone) -> None:
        """Keep a new summary. A turn that waited for it goes on, with the
        newest messages alone if no summary could be made."""
        job = done.job
        if done.text:
            try:
                self._store.set_summary(
                    job.conversation_id, Summary(done.text, job.covers)
                )
            except ConversationStoreFailed:
                pass  # the turn goes on with the newest messages
        turn = self._turn
        if job.turn_id is None or turn is None or turn.id != job.turn_id:
            return
        summary = self._summary(turn.conversation_id)
        kept = self._after_summary(turn.conversation_id, summary)
        if rules.history_chars(kept) > self._history_max_chars:
            kept = list(rules.newest_within(kept, self._history_max_chars))
        self._prepare_turn(turn, summary, kept)

    def _summarize_later(self, conversation_id: str) -> None:
        """After a reply, summarize the older messages in the background once
        the history nears the budget, so the next turn need not wait."""
        summary = self._summary(conversation_id)
        kept = self._after_summary(conversation_id, summary)
        budget = self._history_max_chars
        if not rules.needs_summary(kept, budget):
            return
        fold = rules.fold_point(kept, budget)
        if fold > 0:
            self._ask_summary(conversation_id, summary, kept, fold, None)

    def _prepared(self, prepared: Prepared) -> None:
        """Record what the message meant for the feeling, choose what to keep,
        and ask for the reply in the feeling the message caused."""
        turn = self._turn
        if turn is None or prepared.turn_id != turn.id:
            return  # a turn that was abandoned
        found = prepared.found
        crisis = safety_rules.is_crisis(
            turn.tripwire, found.crisis if found is not None else None
        )
        now = _now()
        lines, importance = (), 1
        if found is not None:
            importance = found.importance
            self._feel_message(turn, found, now, gestures=not crisis)
            if not crisis:
                # A crisis is sensitive, and no rule needs it kept.
                lines = memory_rules.select(
                    found,
                    self._entries(),
                    prepared.vectors,
                    self._calibration,
                    turn.history[-1].text,
                )
        self._ready = _Ready(
            importance, prepared.vectors, prepared.recalled, lines, crisis
        )
        zone = now.tzinfo
        remembered = [
            memory_rules.recalled_line(s.entry, zone) for s in prepared.recalled
        ]
        instructions = [safety_rules.instruction()] if crisis else []
        instructions.append(rules.show_back_instruction(lines))
        mood = "" if crisis else self._mood_line(now)
        turn_text = rules.turn_text(mood, remembered, instructions)
        self._ready = replace(self._ready, turn_text=turn_text)
        self._bridge.askReply.emit(
            ReplyRequest(
                turn_id=turn.id,
                system_prompt=turn.system,
                history=turn.history,
                turn=turn_text,
                tools=not crisis,
                now=now,
                entries=tuple(self._entries()),
                calibration=self._calibration,
            )
        )

    def _feel_message(
        self, turn: _Turn, found: Interpretation, now: datetime, *, gestures: bool
    ) -> None:
        """Record the message as an event, so the feeling moves before the
        reply. A reading the model is not sure of moves nothing."""
        if not emotion_rules.counts(found.event_class, found.confidence):
            return
        payload = {
            "message_id": turn.message_id,
            "class": found.event_class.value,
            "confidence": found.confidence,
        }
        try:
            with self._db.transaction():
                result = self._record(
                    self._state, now, EventKind.USER_MESSAGE, payload,
                    found.importance,
                )
        except (EventLogFailed, CharacterStoreFailed, ValueError):
            return  # no feeling without a recorded cause; the reply still comes
        self._state = result.state
        self._show(result.effects, gestures=gestures)

    def _mood_line(self, now: datetime) -> str:
        """The mood line for the feeling at ``now``, or "" with moods off or no
        character."""
        if not self._state.moods_on:
            return ""
        try:
            point = self._companion.shown_at(self._state, now)
        except (CharacterStoreFailed, ValueError):
            return ""
        return "" if point is None else rules.mood_line(emotion_rules.name(point))

    def _replied(self, text: str, results: Sequence[ToolResult] = ()) -> None:
        """A reply arrived whole. It, and everything the turn keeps, is recorded
        only now and in one transaction, never mid-stream."""
        turn, ready = self._turn, self._ready
        check = self._number_check(text, results, turn, ready)
        self._turn = self._ready = None
        now = _now()
        if ready is not None and ready.crisis:
            if not safety_rules.reply_complies(text):
                text = f"{text}\n\n{safety_rules.required_line()}"
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
                state, effects = self._state, ()
                if turn is not None and ready is not None:
                    state, effects = self._keep(turn, ready, reply, now, state)
        except (MemoryStoreFailed, EventLogFailed) as error:
            self._bridge.replyNotSaved.emit(text, str(error) or NOT_SAVED)
            return
        self._state = state
        self._bridge.replyFinished.emit(text, note, check)
        self._show(effects)
        self._refresh_picker()
        self._refresh_memory()
        self._embed_missing()
        self._summarize_later(conversation_id)

    def _number_check(
        self,
        text: str,
        results: Sequence[ToolResult],
        turn: _Turn | None,
        ready: _Ready | None,
    ) -> str:
        """The chip for numbers in a reply that no data tool, nor the user, nor
        layer 4 gave. Empty after a turn with no data tool."""
        data = [r for r in results if (s := catalog.spec(r.name)) and s.data]
        if not data or turn is None:
            return ""
        sources = [turn.history[-1].text, ready.turn_text if ready else ""]
        sources += [r.text for r in results]
        return tool_rules.number_note(tool_rules.unchecked_numbers(text, sources), data)

    def _answer_tool(self, request: ToolRequested) -> None:
        """Answer a tool that needs the core's data, always with a sentence."""
        try:
            match request.call.name:
                case "why_i_feel":
                    text = self._companion.why(
                        self._state, request.now, request.now.tzinfo
                    )
                case "search_conversations":
                    text = self._search(request)
                case "desk_time":
                    desk = None
                    if self._awareness_on:
                        desk = self._awareness.desk_time(request.now)
                    text = awareness_rules.desk_time_text(desk)
                case "app_usage":
                    minutes = None
                    if self._awareness_on:
                        start = awareness_rules.day_start(request.now)
                        minutes = self._awareness.app_minutes(start, request.now)
                    text = awareness_rules.app_usage_text(minutes)
                case "breathing" | "stretch":
                    text = self._start_activity(request.call.name, request.now)
                case _:
                    text = tool_rules.TOOL_FAILED
        except Exception:  # noqa: BLE001 - the model thread waits for a sentence
            text = tool_rules.TOOL_FAILED
        if not request.answer.cancelled():
            request.answer.set_result(text or tool_rules.TOOL_FAILED)

    def _start_activity(self, name: str, now: datetime) -> str:
        """Record the start of an exercise, then show it. One at a time."""
        if self._activity is not None:
            return tool_rules.ALREADY_RUNNING
        steps = tool_rules.activity(name)
        with self._db.transaction():
            result = self._record(
                self._state, now, EventKind.ACTIVITY_STARTED, {"activity": name}
            )
        self._state, self._activity = result.state, name
        self._show(result.effects)
        self._bridge.activityStarted.emit(name, steps)
        return tool_rules.started(name)

    def _activity_ended(self, name: str, seconds: int) -> None:
        if self._activity != name:
            return
        self._activity = None
        now = _now()
        payload = {"activity": name, "seconds": max(0, int(seconds))}
        try:
            with self._db.transaction():
                result = self._record(
                    self._state, now, EventKind.ACTIVITY_ENDED, payload
                )
        except EventLogFailed:
            return
        self._state = result.state
        self._show(result.effects)

    def _set_awareness(self, on: bool, error: str) -> None:
        """Keep the user's choice and record it, so a replay sees it too."""
        if on == self._awareness_on:
            self._bridge.awarenessChanged.emit(on, error)
            return
        now = _now()
        payload = {"name": awareness_rules.AWARENESS_ON, "value": on}
        try:
            with self._db.transaction():
                self._settings.set_awareness_on(on)
                result = self._record(
                    self._state, now, EventKind.SETTING_CHANGED, payload
                )
        except (SettingNotSaved, EventLogFailed) as failure:
            self._bridge.awarenessChanged.emit(self._awareness_on, str(failure))
            return
        self._awareness_on = on
        self._state = result.state
        self._show(result.effects)
        self._bridge.awarenessChanged.emit(on, error)

    def _presence(self, change: PresenceChange) -> None:
        """Record a change the sampler saw. A report that arrives after desk
        awareness went off is dropped: nothing is read while it is off."""
        if not self._awareness_on:
            return
        try:
            with self._db.transaction():
                result = self._record(
                    self._state, change.at, change.kind, change.payload
                )
                if change.kind == EventKind.APP_HOUR_CLOSED:
                    self._close_hour(change)
        except (EventLogFailed, ValueError):
            return  # the next change is reported as usual
        self._state = result.state
        self._show(result.effects)

    def _close_hour(self, change: PresenceChange) -> None:
        """Keep the minutes of each application in the hour that ended, as the
        day it belongs to and its local hour."""
        start = datetime.fromisoformat(str(change.payload["hour_start"]))
        minutes = self._awareness.app_minutes(start, start + timedelta(hours=1))
        day = awareness_rules.day_start(start).date().isoformat()
        self._app_usage.put(day, start.hour, minutes)

    def _search(self, request: ToolRequested) -> str:
        """Earlier messages that hold the words, not counting the message the
        user just sent."""
        query = str(request.call.arguments.get("query", ""))
        current = self._turn.message_id if self._turn is not None else None
        found = self._store.search(query, rules.SEARCH_LIMIT, current)
        return rules.found_text(query, found, request.now.tzinfo)

    def _keep(self, turn: _Turn, ready: _Ready, reply: Message, now: datetime, state):
        """Store the chosen lines with their events, and link what the reply drew
        on. Runs inside the caller's transaction. Returns the state and the
        effects to show after the commit."""
        stored = self._memory.remember(
            ready.lines, ready.importance, turn.message_id, ready.vectors, now
        )
        effects: list[Effect] = []
        for entry in stored:
            result = self._record(
                state, now, EventKind.MEMORY_STORED, {"memory_item_id": entry.id}
            )
            state = result.state
            effects.extend(result.effects)
        self._memory.use(reply.id, [s.entry for s in ready.recalled], now)
        return state, tuple(effects)

    def _reply_lost(self, text: str) -> None:
        turn = self._turn
        self._turn = self._ready = None
        if turn is not None and turn.tripwire:
            # The safety line must reach a crisis message even with no reply.
            text = f"{text}\n\n{safety_rules.required_line()}"
        self._bridge.replyFailed.emit(text)

    def _is_current(self, turn_id: int) -> bool:
        """Whether a model result belongs to the turn in flight. A result for
        an abandoned turn is dropped."""
        return self._turn is not None and self._turn.id == turn_id

    def _idle(self) -> bool:
        """No reply in flight. The window locks these controls during a reply,
        so a command that still arrives only resynchronises the picker."""
        if self._turn is None:
            return True
        self._refresh_picker()
        return False

    def _preview_deletion(self, conversation_id: str) -> None:
        conversation = next(
            (c for c in self._store.conversations() if c.id == conversation_id), None
        )
        if conversation is None:
            return
        ids = {m.id for m in self._store.history(conversation_id)}
        lines = memory_rules.from_messages(self._entries(), ids)
        self._bridge.conversationDeletionPreviewed.emit(
            conversation, len(ids), len(lines)
        )

    def _delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation and every line the user told in it, with their
        events, in one transaction."""
        now = _now()
        ids = {m.id for m in self._store.history(conversation_id)}
        state, effects = self._state, []
        try:
            lines = memory_rules.from_messages(self._memory.entries(), ids)
            with self._db.transaction():
                for entry in lines:
                    self._memory.remove(entry)
                    result = self._record(
                        state, now, EventKind.MEMORY_REMOVED,
                        {"memory_item_id": entry.id},
                    )
                    state = result.state
                    effects.extend(result.effects)
                self._store.delete(conversation_id)
        except (MemoryStoreFailed, EventLogFailed, ConversationStoreFailed) as error:
            self._bridge.conversationFailed.emit(str(error))
            return
        self._state = state
        self._show(effects)
        if conversation_id == self._conversation.id:
            self._conversation = self._store.latest() or self._store.create(now)
            self._bridge.conversationLoaded.emit(
                self._store.history(self._conversation.id)
            )
        self._refresh_picker()
        self._refresh_memory()

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

    def _entries(self) -> list[MemoryItem]:
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
        self._bridge.memoryShown.emit(entries)

    def _correct(self, entry: MemoryItem, text: str) -> None:
        try:
            self._memory.correct(entry, text)
        except ValueError:
            pass  # the view refuses a blank line before it gets here
        except MemoryStoreFailed as error:
            self._bridge.memoryFailed.emit(str(error))
            return
        self._refresh_memory()
        self._embed_missing()

    def _remove(self, entry: MemoryItem) -> None:
        now = _now()
        kind, payload = EventKind.MEMORY_REMOVED, {"memory_item_id": entry.id}
        try:
            with self._db.transaction():
                self._memory.remove(entry)
                result = self._record(self._state, now, kind, payload)
        except (MemoryStoreFailed, EventLogFailed) as error:
            self._bridge.memoryFailed.emit(str(error))
            return
        self._state = result.state
        self._show(result.effects)
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
                result = self._record(
                    self._state, now, EventKind.CHARACTER_CHANGED,
                    {"version_id": version.id},
                )
        except (CharacterStoreFailed, EventLogFailed, ValueError) as error:
            self._bridge.characterFailed.emit(str(error))
            return
        self._state = result.state
        self._show(result.effects)
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
                    result = self._record(
                        self._state, now, EventKind.CHARACTER_CHANGED,
                        {"version_id": self._version.id},
                    )
                self._state = result.state
                self._show(result.effects)
            except EventLogFailed:
                pass
        self._conversation = self._store.latest() or self._store.create(_now())
        self._bridge.conversationLoaded.emit(self._store.history(self._conversation.id))
        self._refresh_picker()
        self._refresh_memory()
        # Erasing everything returns the settings to their defaults.
        self._awareness_on = self._settings.awareness_on()
        self._bridge.awarenessChanged.emit(self._awareness_on, "")

    # ── events ────────────────────────────────────────────────────────────

    def _record(
        self,
        state,
        now: datetime,
        kind: EventKind,
        payload: Payload,
        importance: int | None = None,
    ) -> StepResult:
        return self._companion.record(
            state, now, _offset(now), kind, payload, importance
        )

    def _show(self, effects, *, gestures: bool = True) -> None:
        """Carry out the effects of committed events. No gesture on a crisis
        turn: nothing should look playful there."""
        for effect in effects:
            match effect:
                case ShowExpression(expression):
                    self._bridge.expressionChanged.emit(
                        expression.preset, expression.weight
                    )
                case ShowGesture(name) if gestures:
                    self._bridge.gestureShown.emit(name)

    def _show_face(self) -> None:
        """The face for the feeling now, at start."""
        try:
            point = self._companion.shown_at(self._state, _now())
        except (CharacterStoreFailed, ValueError):
            return
        if point is not None:
            face = emotion_rules.expression(point, self._state.moods_on)
            self._bridge.expressionChanged.emit(face.preset, face.weight)

    def _fold(self):
        try:
            return self._companion.start()
        except (EventLogFailed, ValueError):
            return companion_rules.initial_state()
