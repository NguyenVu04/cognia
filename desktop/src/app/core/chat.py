"""Conversations: a message, its reply, the tools of the reply, and the
conversation picker."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING

from src.app.chat_worker import (
    Prepared,
    ReplyRequest,
    SummaryDone,
    SummaryJob,
    TurnRequest,
)
from src.app.commands import (
    ActivityEnded,
    DeleteConversation,
    NewConversation,
    OpenConversation,
    PreviewConversationDeletion,
    RateMessage,
    ReplyArrived,
    ReplyLost,
    SendMessage,
    StartActivity,
    SummaryMade,
    ToolRequested,
    TurnPrepared,
    VectorsMade,
)
from src.domain.awareness import rules as awareness_rules
from src.domain.conversation import rules
from src.domain.conversation.models import (
    COMPANION,
    USER,
    Interpretation,
    Message,
    Summary,
)
from src.domain.emotion import rules as emotion_rules
from src.domain.events.models import EventKind
from src.domain.memory import rules as memory_rules
from src.domain.memory.models import MemoryItem, Scored, Vector
from src.domain.ports import (
    CharacterStoreFailed,
    ConversationStoreFailed,
    EventLogFailed,
    MemoryStoreFailed,
)
from src.domain.safety import rules as safety_rules
from src.domain.tools import catalog
from src.domain.tools import rules as tool_rules
from src.domain.tools.models import ToolResult
from src.infrastructure.storage.sqlite_store import UNTITLED, title_from

if TYPE_CHECKING:
    from src.app.core_host import CoreHost

NOT_SAVED = "The reply could not be saved, so nothing from it was kept. Try again."
SHORT_REPLIES = "Keep your reply short: the user likes short messages."


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


class ChatHandler:
    handles = (
        SendMessage, TurnPrepared, SummaryMade, ReplyArrived, ReplyLost,
        ToolRequested, NewConversation, OpenConversation,
        PreviewConversationDeletion, DeleteConversation, VectorsMade,
        RateMessage, ActivityEnded, StartActivity,
    )

    def __init__(self, core: CoreHost) -> None:
        self.core = core
        self.conversation = None
        self._turn: _Turn | None = None
        self._ready: _Ready | None = None
        self._turn_count = 0
        self.activity: str | None = None

    def start(self) -> None:
        store = self.core.conversations
        self.conversation = store.latest() or store.create(self.core.clock())
        self.core.bridge.conversationLoaded.emit(store.history(self.conversation.id))
        self.refresh_picker()

    def handle(self, item) -> None:
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
            case ReplyLost(turn_id, text) if self._is_current(turn_id):
                self._reply_lost(text)
            case NewConversation() if self.idle():
                self._new_conversation()
            case OpenConversation(conversation_id) if self.idle():
                self._open_conversation(conversation_id)
            case PreviewConversationDeletion(conversation_id) if self.idle():
                self._preview_deletion(conversation_id)
            case DeleteConversation(conversation_id) if self.idle():
                self._delete_conversation(conversation_id)
            case VectorsMade(pairs):
                self.core.memory_handler.embedded(pairs)
            case RateMessage(message_id, rating):
                self._rate(message_id, rating)
            case ActivityEnded(activity, seconds):
                self._activity_ended(activity, seconds)
            case StartActivity(activity):
                self.start_activity(activity, self.core.clock())

    # ── the turn ──────────────────────────────────────────────────────────

    def _send(self, text: str) -> None:
        """The user has said something. Record it, show it, then prepare."""
        core = self.core
        if core.character.version is None:
            core.character.show_templates(None)
            return
        now = core.clock()
        conversation = self.conversation
        message = core.conversations.append(
            Message.new(conversation.id, USER, text, now)
        )
        if conversation.title == UNTITLED:
            core.conversations.retitle(conversation.id, title_from(text))
            self.conversation = self._reread(conversation.id)
        core.bridge.messageAppended.emit(message)
        self.refresh_picker()
        core.proactive.user_spoke(now)

        self._turn_count += 1
        turn = _Turn(
            self._turn_count, conversation.id, message.id, (),
            safety_rules.tripwire(text),
        )
        self._turn, self._ready = turn, None
        summary = self._summary(conversation.id)
        kept = self._after_summary(conversation.id, summary)
        budget = core.history_max_chars
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
        now = self.core.clock()
        turn = replace(
            turn,
            history=tuple(history),
            system=rules.with_summary(self.core.character.prompt, summary),
        )
        self._turn = turn
        self.core.bridge.askPrepare.emit(
            TurnRequest(
                turn_id=turn.id,
                system_prompt=turn.system,
                history=turn.history,
                entries=tuple(self.entries()),
                crisis=turn.tripwire,
                today=now.date(),
                now=now,
                calibration=self.core.calibration,
            )
        )

    def _summary(self, conversation_id: str) -> Summary | None:
        try:
            return self.core.conversations.summary(conversation_id)
        except ConversationStoreFailed:
            return None  # the history is then cut instead

    def _after_summary(
        self, conversation_id: str, summary: Summary | None
    ) -> list[Message]:
        """The messages that the summary does not cover."""
        messages = self.core.conversations.history(conversation_id)
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
        self.core.bridge.askSummary.emit(
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
                self.core.conversations.set_summary(
                    job.conversation_id, Summary(done.text, job.covers)
                )
            except ConversationStoreFailed:
                pass  # the turn goes on with the newest messages
        turn = self._turn
        if job.turn_id is None or turn is None or turn.id != job.turn_id:
            return
        summary = self._summary(turn.conversation_id)
        kept = self._after_summary(turn.conversation_id, summary)
        budget = self.core.history_max_chars
        if rules.history_chars(kept) > budget:
            kept = list(rules.newest_within(kept, budget))
        self._prepare_turn(turn, summary, kept)

    def _summarize_later(self, conversation_id: str) -> None:
        """After a reply, summarize the older messages in the background once
        the history nears the budget, so the next turn need not wait."""
        summary = self._summary(conversation_id)
        kept = self._after_summary(conversation_id, summary)
        budget = self.core.history_max_chars
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
        now = self.core.clock()
        entries = self.entries()
        lines, importance = (), 1
        if found is not None:
            importance = found.importance
            self._feel_message(turn, found, now, gestures=not crisis)
            if not crisis:
                # A crisis is sensitive, and no rule needs it kept.
                lines = memory_rules.select(
                    found, entries, prepared.vectors, self.core.calibration,
                    turn.history[-1].text,
                )
        zone = now.tzinfo
        remembered = [
            memory_rules.recalled_line(s.entry, zone) for s in prepared.recalled
        ]
        instructions = [safety_rules.instruction()] if crisis else []
        instructions.append(rules.show_back_instruction(lines))
        if self.core.learning.wants_short_replies():
            instructions.append(SHORT_REPLIES)
        mood = "" if crisis else self._mood_line(now)
        turn_text = rules.turn_text(mood, remembered, instructions)
        self._ready = _Ready(
            importance, prepared.vectors, prepared.recalled, lines, crisis, turn_text
        )
        self.core.bridge.askReply.emit(
            ReplyRequest(
                turn_id=turn.id,
                system_prompt=turn.system,
                history=turn.history,
                turn=turn_text,
                tools=not crisis,
                now=now,
                entries=tuple(entries),
                calibration=self.core.calibration,
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
            "chars": len(turn.history[-1].text) if turn.history else 0,
        }
        core = self.core
        try:
            with core.db.transaction():
                result = core.record(EventKind.USER_MESSAGE, payload, now,
                                     found.importance)
        except (EventLogFailed, CharacterStoreFailed, ValueError):
            return  # no feeling without a recorded cause; the reply still comes
        core.commit(result, gestures=gestures)

    def _mood_line(self, now: datetime) -> str:
        """The mood line for the feeling at ``now``, or "" with moods off or no
        character."""
        if not self.core.state.moods_on:
            return ""
        point = self.core.feeling_point(now)
        return "" if point is None else rules.mood_line(emotion_rules.name(point))

    def _replied(self, text: str, results: Sequence[ToolResult] = ()) -> None:
        """A reply arrived whole. It, and everything the turn keeps, is recorded
        only now and in one transaction, never mid-stream."""
        core = self.core
        turn, ready = self._turn, self._ready
        check = self._number_check(text, results, turn, ready)
        self._turn = self._ready = None
        now = core.clock()
        if ready is not None and ready.crisis:
            if not safety_rules.reply_complies(text):
                text = f"{text}\n\n{safety_rules.required_line()}"
        note = ""
        if ready is not None and ready.lines:
            missing = [
                line for line in ready.lines if not memory_rules.shows_back(text, line)
            ]
            note = memory_rules.stored_note(missing, now.date())
        conversation_id = turn.conversation_id if turn else self.conversation.id
        results_kept = []
        try:
            with core.db.transaction():
                reply = core.conversations.append(
                    Message.new(conversation_id, COMPANION, text, now)
                )
                if turn is not None and ready is not None:
                    results_kept = self._keep(turn, ready, reply, now)
        except (MemoryStoreFailed, EventLogFailed) as error:
            core.bridge.replyNotSaved.emit(text, str(error) or NOT_SAVED)
            return
        core.bridge.replyFinished.emit(text, note, check, reply.id)
        for result in results_kept:
            core.commit(result)
        self.refresh_picker()
        core.memory_handler.refresh()
        core.memory_handler.embed_missing()
        self._summarize_later(conversation_id)

    def _number_check(
        self,
        text: str,
        results: Sequence[ToolResult],
        turn: _Turn | None,
        ready: _Ready | None,
    ) -> str:
        """The chip for numbers in a reply that no data tool, nor the user, nor
        the turn's own text gave. Empty after a turn with no data tool."""
        data = [r for r in results if (s := catalog.spec(r.name)) and s.data]
        if not data or turn is None:
            return ""
        sources = [turn.history[-1].text, ready.turn_text if ready else ""]
        sources += [r.text for r in results]
        return tool_rules.number_note(tool_rules.unchecked_numbers(text, sources), data)

    def _keep(self, turn: _Turn, ready: _Ready, reply: Message, now: datetime):
        """Store the chosen lines with their events, and link what the reply drew
        on. Runs inside the caller's transaction. Returns the results to
        commit after it."""
        core = self.core
        stored = core.memory.remember(
            ready.lines, ready.importance, turn.message_id, ready.vectors, now
        )
        results = []
        state = core.state
        for entry in stored:
            result = core.companion.record(
                state, now, _offset(now), EventKind.MEMORY_STORED,
                {"memory_item_id": entry.id}, None,
            )
            state = result.state
            results.append(result)
        core.memory.use(reply.id, [s.entry for s in ready.recalled], now)
        return results

    def _answer_tool(self, request: ToolRequested) -> None:
        """Answer a tool that needs the core's data, always with a sentence."""
        core = self.core
        try:
            match request.call.name:
                case "why_i_feel":
                    text = core.companion.why(
                        core.state, request.now, request.now.tzinfo
                    )
                case "search_conversations":
                    text = self._search(request)
                case "desk_time":
                    desk = None
                    if core.desk.awareness_on:
                        desk = core.awareness.desk_time(request.now)
                    text = awareness_rules.desk_time_text(desk)
                case "app_usage":
                    minutes = None
                    if core.desk.awareness_on:
                        start = awareness_rules.day_start(request.now)
                        minutes = core.awareness.app_minutes(start, request.now)
                    text = awareness_rules.app_usage_text(minutes)
                case "breathing" | "stretch":
                    text = self.start_activity(request.call.name, request.now)
                case _:
                    text = tool_rules.TOOL_FAILED
        except Exception:  # noqa: BLE001 - the model thread waits for a sentence
            text = tool_rules.TOOL_FAILED
        if not request.answer.cancelled():
            request.answer.set_result(text or tool_rules.TOOL_FAILED)

    def _search(self, request: ToolRequested) -> str:
        """Earlier messages that hold the words, not counting the message the
        user just sent."""
        query = str(request.call.arguments.get("query", ""))
        current = self._turn.message_id if self._turn is not None else None
        found = self.core.conversations.search(query, rules.SEARCH_LIMIT, current)
        return rules.found_text(query, found, request.now.tzinfo)

    def _reply_lost(self, text: str) -> None:
        turn = self._turn
        self._turn = self._ready = None
        if turn is not None and turn.tripwire:
            # The safety line must reach a crisis message even with no reply.
            text = f"{text}\n\n{safety_rules.required_line()}"
        self.core.bridge.replyFailed.emit(text)

    def _is_current(self, turn_id: int) -> bool:
        """Whether a model result belongs to the turn in flight."""
        return self._turn is not None and self._turn.id == turn_id

    def idle(self) -> bool:
        """No reply in flight. The window locks these controls during a reply,
        so a command that still arrives only resynchronises the picker."""
        if self._turn is None:
            return True
        self.refresh_picker()
        return False

    def abandon(self) -> None:
        """Nothing from a turn in flight may be kept."""
        self._turn = self._ready = None

    # ── exercises ─────────────────────────────────────────────────────────

    def start_activity(self, name: str, now: datetime) -> str:
        """Record the start of an exercise, then show it. One at a time."""
        if self.activity is not None:
            return tool_rules.ALREADY_RUNNING
        steps = tool_rules.activity(name)
        result = self.core.record_now(
            EventKind.ACTIVITY_STARTED, {"activity": name}, now
        )
        if result is None:
            return tool_rules.TOOL_FAILED
        self.activity = name
        self.core.bridge.activityStarted.emit(name, steps)
        return tool_rules.started(name)

    def _activity_ended(self, name: str, seconds: int) -> None:
        if self.activity != name:
            return
        self.activity = None
        payload = {"activity": name, "seconds": max(0, int(seconds))}
        self.core.record_now(EventKind.ACTIVITY_ENDED, payload)

    # ── ratings ───────────────────────────────────────────────────────────

    def _rate(self, message_id: str, rating: int) -> None:
        """Keep the rating, as evidence of what the user liked."""
        core = self.core
        kept = rating if rating in (1, -1) else None
        try:
            with core.db.transaction():
                core.conversations.rate(message_id, kept)
                result = core.record(
                    EventKind.MESSAGE_RATED,
                    {"message_id": message_id, "rating": kept or 0},
                )
        except (ConversationStoreFailed, EventLogFailed, ValueError) as error:
            core.bridge.noticeShown.emit(str(error))
            return
        core.commit(result)

    # ── the picker ────────────────────────────────────────────────────────

    def _preview_deletion(self, conversation_id: str) -> None:
        conversation = self._find(conversation_id)
        if conversation is None:
            return
        ids = {m.id for m in self.core.conversations.history(conversation_id)}
        lines = memory_rules.from_messages(self.entries(), ids)
        self.core.bridge.conversationDeletionPreviewed.emit(
            conversation, len(ids), len(lines)
        )

    def _delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation and every line the user told in it, with their
        events, in one transaction."""
        core = self.core
        now = core.clock()
        ids = {m.id for m in core.conversations.history(conversation_id)}
        state, results = core.state, []
        try:
            lines = memory_rules.from_messages(core.memory.entries(), ids)
            with core.db.transaction():
                for entry in lines:
                    core.memory.remove(entry)
                    result = core.companion.record(
                        state, now, _offset(now), EventKind.MEMORY_REMOVED,
                        {"memory_item_id": entry.id}, None,
                    )
                    state = result.state
                    results.append(result)
                core.conversations.delete(conversation_id)
        except (MemoryStoreFailed, EventLogFailed, ConversationStoreFailed) as error:
            core.bridge.conversationFailed.emit(str(error))
            return
        for result in results:
            core.commit(result)
        if conversation_id == self.conversation.id:
            self.conversation = (
                core.conversations.latest() or core.conversations.create(now)
            )
            core.bridge.conversationLoaded.emit(
                core.conversations.history(self.conversation.id)
            )
        self.refresh_picker()
        core.memory_handler.refresh()

    def _new_conversation(self) -> None:
        store = self.core.conversations
        if not store.history(self.conversation.id, 1):
            return  # already sitting in an empty one; don't pile up more
        self.conversation = store.create(self.core.clock())
        self.core.bridge.conversationLoaded.emit([])
        self.refresh_picker()

    def _open_conversation(self, conversation_id: str) -> None:
        if conversation_id == self.conversation.id:
            return
        self.conversation = self._reread(conversation_id)
        self.core.bridge.conversationLoaded.emit(
            self.core.conversations.history(conversation_id)
        )
        self.refresh_picker()

    def _find(self, conversation_id: str):
        return next(
            (c for c in self.core.conversations.conversations()
             if c.id == conversation_id),
            None,
        )

    def _reread(self, conversation_id: str):
        return self._find(conversation_id) or self.conversation

    def refresh_picker(self) -> None:
        self.core.bridge.conversationsChanged.emit(
            self.core.conversations.conversations(), self.conversation.id
        )

    def after_erasure(self) -> None:
        store = self.core.conversations
        self.conversation = store.latest() or store.create(self.core.clock())
        self.core.bridge.conversationLoaded.emit(store.history(self.conversation.id))
        self.refresh_picker()

    def entries(self) -> list[MemoryItem]:
        try:
            return self.core.memory.entries()
        except MemoryStoreFailed:
            return []

    def add_greeting(self, text: str, note: str, at: datetime) -> Message | None:
        """Keep the greeting of the day as a companion message."""
        try:
            message = self.core.conversations.append(
                Message.new(self.conversation.id, COMPANION, text, at)
            )
        except ConversationStoreFailed:
            return None
        self.refresh_picker()
        return message


def _offset(moment: datetime) -> int:
    return int(moment.utcoffset().total_seconds() // 60)

