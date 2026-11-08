"""Everything the companion does on its own, through the SpeechGate.

The initiative rules find a reason to speak; the gate decides whether the
moment allows it; the message waits for a pause in typing; the model words it;
the gate checks the words and records the decision; only then does the window
show it. Pause, the greeting of the day and the user's answers live here too.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from src.app.chat_worker import WordJob
from src.app.commands import (
    CompanionShown,
    Pause,
    RespondToMessage,
    Resume,
    SaveSpeechSettings,
    SetKind,
    WindowOpened,
    Worded,
)
from src.domain.awareness.rules import day_start
from src.domain.companion.rules import MOODS_ON
from src.domain.events.models import Event, EventKind
from src.domain.initiative import rules as initiative
from src.domain.initiative.models import ACTIVE, Context, InitiativeState
from src.domain.memory.models import TOLD
from src.domain.ports import EventLogFailed, MemoryStoreFailed
from src.domain.ports.decision_store import DecisionStoreFailed
from src.domain.speech import rules as speech
from src.domain.speech.models import (
    Candidate,
    MessageKind,
    Moment,
    Outcome,
    ProactiveMessage,
    Response,
    SpeechSettings,
)
from src.infrastructure.storage.settings_store import SettingNotSaved
from src.utils import paths

if TYPE_CHECKING:
    from src.app.core_host import CoreHost

_NEEDS_CEILING = {MessageKind.BREAK, MessageKind.REMARK, MessageKind.QUESTION}
# These kinds are said in plain words; the model does not word them.
_PLAIN = {MessageKind.ADJUSTMENT}
_HINTS = {
    MessageKind.BREAK: (
        "Suggest a short break, kindly. Never say they are working. You may "
        "offer to breathe or stretch together."
    ),
    MessageKind.REMARK: "Say something friendly: you have not talked for a while.",
    MessageKind.QUESTION: "Ask this question in your own words: {question}",
    MessageKind.GREETING: "Greet the user for the first time today.",
    MessageKind.RETURN: "Welcome the user back. Never reproach them.",
}


@dataclass(frozen=True)
class _Waiting:
    candidate: Candidate
    since: datetime


@dataclass(frozen=True)
class _Shown:
    kind: MessageKind
    at: datetime


def load_questions() -> tuple[tuple[str, str], ...]:
    """The questions to get to know the user, as (id, text)."""
    try:
        text = paths.resource("questions.toml").read_text(encoding="utf-8")
        return tuple((q["id"], q["text"]) for q in tomllib.loads(text)["question"])
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError):
        return ()


class ProactiveHandler:
    handles = (
        WindowOpened,
        Worded,
        RespondToMessage,
        SetKind,
        SaveSpeechSettings,
        CompanionShown,
        Pause,
        Resume,
    )

    def __init__(self, core: CoreHost) -> None:
        self.core = core
        self.state = InitiativeState()
        self.settings = SpeechSettings.defaults()
        self.questions = load_questions()
        self.hidden = False
        self.paused_at: datetime | None = None
        self.paused_until: datetime | None = None
        self.paused = False
        self._waiting: list[_Waiting] = []
        self._held: list[Candidate] = []
        self._wording: dict[int, tuple[Candidate, float]] = {}
        self._shown: dict[str, _Shown] = {}
        self._jobs = 0

    # ── state ─────────────────────────────────────────────────────────────

    def fold(self, events: Iterable[Event]) -> None:
        state = InitiativeState()
        context = self._context()
        for event in events:
            state = initiative.step(state, event, context).state
            if event.kind == EventKind.WINDOW_OPENED:
                state = replace(state, greeted_on=day_start(event.occurred_at).date())
        # Nothing is known about the desk until the sampler reports again.
        self.state = replace(
            state,
            desk="unknown",
            talk_at=None,
            break_at=None,
            doze_at=None,
            away_since=None,
            run_start_at=None,
            run_start_seq=None,
        )

    def _context(self) -> Context:
        core = self.core
        point = core.feeling_point() if core.db is not None else None
        name = core.feeling_name() if point is not None else "calm"
        return Context(
            feeling=name,
            arousal=point.arousal if point is not None else 0.0,
            threshold_min=self.settings.break_threshold_min,
            learned=core.learning.timing(),
            questions=self.questions,
        )

    def start(self) -> None:
        core = self.core
        self.settings = core.settings.speech()
        core.bridge.speechSettingsShown.emit(self.settings)
        self.hidden = core.settings.placement().hidden
        at, until, paused = core.settings.paused_until()
        self.paused, self.paused_at, self.paused_until = paused, at, until
        if paused and until is not None and until <= core.clock():
            self._resume()
            return
        core.bridge.pauseChanged.emit(
            paused, _until_text(until, core.clock()) if paused else "", ""
        )

    def handle(self, item) -> None:
        match item:
            case WindowOpened():
                self._window_opened()
            case Worded(job_id, text):
                self._worded(job_id, text)
            case RespondToMessage(decision_id, response):
                self._respond(decision_id, response)
            case SetKind(kind, enabled):
                self._set_kind(kind, enabled)
            case SaveSpeechSettings(chosen):
                self._save(chosen)
            case CompanionShown(shown):
                self._companion_shown(shown)
            case Pause(until):
                self._pause(until)
            case Resume():
                self._resume()

    # ── events and timers ─────────────────────────────────────────────────

    def observe(self, event: Event) -> None:
        """Step the initiative rules with a recorded event."""
        if event.kind == EventKind.TYPING_PAUSE:
            self._typing_paused(event.occurred_at)
            return
        step = initiative.step(self.state, event, self._context())
        self.state = step.state
        if step.ambient:
            self.core.bridge.ambientChanged.emit(step.ambient)
        if step.lapse:
            self._lapse(step.lapse, event.occurred_at)
        for candidate in step.candidates:
            self.consider(candidate)

    def next_wake(self) -> datetime | None:
        times = [initiative.next_wake(self.state)]
        times += [s.at + initiative.PASS_OVER_AFTER for s in self._shown.values()]
        if self.paused and self.paused_until is not None:
            times.append(self.paused_until)
        times = [t for t in times if t is not None]
        return min(times) if times else None

    def wake(self, now: datetime) -> None:
        if self.paused:
            if self.paused_until is not None and self.paused_until <= now:
                self._resume()
            return
        for decision_id, shown in list(self._shown.items()):
            if shown.at + initiative.PASS_OVER_AFTER <= now:
                self._passed_over(decision_id, shown, now)
        purposes = initiative.due(self.state, now)
        if purposes:
            self.core.record_now(EventKind.TIMER, {"purposes": list(purposes)}, now)

    # ── the gate ──────────────────────────────────────────────────────────

    def _moment(self, at: datetime, *, visible: bool = False) -> Moment:
        core = self.core
        try:
            sent = core.speech.sent_since(day_start(at))
        except DecisionStoreFailed:
            sent = 0
        return Moment(
            at=at,
            at_desk=initiative.at_desk_now(self.state),
            locked=core.desk.locked,
            presenting=core.desk.presenting,
            typing=False,
            hidden=self.hidden and not visible,
            sent_today=sent,
        )

    def consider(self, candidate: Candidate, *, visible: bool = False) -> None:
        """Pass a reason to speak through the gate. One that may speak waits
        for a pause in typing."""
        if self.paused or self.core.character.version is None:
            return
        now = self.core.clock()
        moment = self._moment(now, visible=visible)
        if candidate.kind in _NEEDS_CEILING:
            ceiling = speech.ceiling_factor(self.settings, moment.sent_today)
            candidate = replace(candidate, factors=(*candidate.factors, ceiling))
        try:
            verdict = self.core.speech.consider(candidate, moment, self.settings)
        except DecisionStoreFailed:
            return
        if verdict.outcome is Outcome.HELD:
            self._held.append(candidate)
            return
        if not verdict.passes:
            return
        if self.core.desk.awareness_on and self.state.desk == ACTIVE:
            self._waiting.append(_Waiting(candidate, now))
            self.core.bridge.watchForPause.emit()
        else:
            self._word(candidate, 0.0)

    def _typing_paused(self, at: datetime) -> None:
        waiting, self._waiting = self._waiting, []
        for item in waiting:
            if self.state.desk == ACTIVE:
                self._word(item.candidate, (at - item.since).total_seconds())
            else:
                self._drop(item.candidate, at, "away")

    def _word(self, candidate: Candidate, delay_s: float) -> None:
        if candidate.kind in _PLAIN:
            self._release(candidate, None, delay_s)
            return
        self._jobs += 1
        self._wording[self._jobs] = (candidate, delay_s)
        self.core.bridge.askWord.emit(
            WordJob(self._jobs, self.core.character.prompt, _instruction(candidate))
        )

    def _worded(self, job_id: int, text: str) -> None:
        found = self._wording.pop(job_id, None)
        if found is None:
            return
        candidate, delay_s = found
        self._release(candidate, text.strip() or None, delay_s)

    def _release(
        self,
        candidate: Candidate,
        words: str | None,
        delay_s: float,
        *,
        visible: bool = False,
    ) -> None:
        if self.paused:
            return
        moment = self._moment(self.core.clock(), visible=visible)
        try:
            verdict, message = self.core.speech.release(
                candidate, words, moment, self.settings, delay_s
            )
        except DecisionStoreFailed:
            return
        if verdict.outcome is Outcome.HELD:
            self._held.append(candidate)
            return
        if message is not None:
            self._show(message)

    def _show(self, message: ProactiveMessage) -> None:
        core = self.core
        payload = {
            "decision_id": message.decision_id,
            "kind": message.kind.value,
            "at_desk": self.state.desk == ACTIVE,
        }
        core.record_now(EventKind.MESSAGE_SHOWN, payload, message.shown_at)
        if message.kind is MessageKind.GREETING:
            note = " ".join(message.reasons)
            stored = core.chat.add_greeting(message.text, note, message.shown_at)
            if stored is not None:
                core.bridge.greetingShown.emit(stored, note)
            return
        self._shown[message.decision_id] = _Shown(message.kind, message.shown_at)
        core.bridge.proactiveShown.emit(message)

    def _drop(self, candidate: Candidate, at: datetime, reason: str) -> None:
        try:
            self.core.speech.drop(candidate, at, reason)
        except DecisionStoreFailed:
            pass

    def _lapse(self, reason: str, at: datetime) -> None:
        """The reasons to speak no longer hold: nothing waiting is said late."""
        for item in self._waiting:
            self._drop(item.candidate, at, reason)
        for candidate in self._held:
            self._drop(candidate, at, reason)
        self._waiting, self._held = [], []
        self._wording.clear()

    # ── the user's answers ────────────────────────────────────────────────

    def _respond(self, decision_id: str, response: str) -> None:
        shown = self._shown.pop(decision_id, None)
        if shown is None:
            return
        self._answer(decision_id, shown, response)

    def _answer(self, decision_id: str, shown: _Shown, response: str) -> None:
        core = self.core
        try:
            core.speech.respond(decision_id, response)
        except DecisionStoreFailed:
            pass
        core.record_now(
            EventKind.MESSAGE_ANSWERED,
            {
                "decision_id": decision_id,
                "kind": shown.kind.value,
                "at_desk": self.state.desk == ACTIVE,
                "response": response,
            },
        )

    def _passed_over(self, decision_id: str, shown: _Shown, now: datetime) -> None:
        core = self.core
        self._shown.pop(decision_id, None)
        try:
            core.speech.respond(decision_id, Response.PASSED_OVER.value)
        except DecisionStoreFailed:
            pass
        core.record_now(
            EventKind.MESSAGE_PASSED_OVER,
            {
                "decision_id": decision_id,
                "kind": shown.kind.value,
                "at_desk": self.state.desk == ACTIVE,
                "response": Response.PASSED_OVER.value,
            },
            now,
        )
        core.bridge.proactiveShown.emit(None)

    def user_spoke(self, at: datetime) -> None:
        """Talking answers a message on screen; a break suggestion stays."""
        for decision_id, shown in list(self._shown.items()):
            if shown.kind is not MessageKind.BREAK:
                self._shown.pop(decision_id)
                self._answer(decision_id, shown, Response.ANSWERED.value)
                self.core.bridge.proactiveShown.emit(None)

    # ── the greeting ──────────────────────────────────────────────────────

    def _window_opened(self) -> None:
        core = self.core
        if self.hidden and self._held:
            held, self._held = self._held, []
            for candidate in held:
                self.consider(candidate, visible=True)
        if not initiative.first_opening(self.state.greeted_on, core.clock()):
            return
        result = core.record_now(EventKind.WINDOW_OPENED, {})
        if result is None or result.event is None or core.character.version is None:
            return
        self.state, candidate = initiative.greeting(
            self.state,
            result.event,
            self._told_line(result.event.occurred_at),
            self._context(),
        )
        if candidate is not None:
            self.consider(candidate, visible=True)

    def _told_line(self, now: datetime) -> tuple[str, str] | None:
        """The latest line the user told on the last day they talked before
        today."""
        try:
            entries = self.core.memory.entries()
        except MemoryStoreFailed:
            return None
        today = day_start(now)
        earlier = [e for e in entries if e.kind == TOLD and e.recorded_at < today]
        if not earlier:
            return None
        latest = max(earlier, key=lambda e: e.recorded_at)
        return latest.id, latest.text

    # ── settings ──────────────────────────────────────────────────────────

    def _set_kind(self, kind: MessageKind, enabled: bool) -> None:
        try:
            self.core.settings.set_kind(kind, enabled)
        except SettingNotSaved as error:
            self.core.bridge.noticeShown.emit(str(error))
            return
        self.settings = self.core.settings.speech()
        self.core.bridge.speechSettingsShown.emit(self.settings)

    def _save(self, chosen: SpeechSettings) -> None:
        core = self.core
        before = self.settings
        try:
            with core.db.transaction():
                core.settings.set_speech(chosen)
                result = None
                if chosen.moods_on != before.moods_on:
                    result = core.record(
                        EventKind.SETTING_CHANGED,
                        {"name": MOODS_ON, "value": chosen.moods_on},
                    )
        except (SettingNotSaved, EventLogFailed) as error:
            core.bridge.speechSettingsSaved.emit(str(error))
            return
        self.settings = core.settings.speech()
        if result is not None:
            core.commit(result)
            core.show_feeling(force=True)
        # Shown first: showing the settings clears the line that says saved.
        core.bridge.speechSettingsShown.emit(self.settings)
        core.bridge.speechSettingsSaved.emit("")

    def _companion_shown(self, shown: bool) -> None:
        self.hidden = not shown
        try:
            self.core.settings.set_hidden(not shown)
        except SettingNotSaved:
            pass
        if shown and self._held:
            held, self._held = self._held, []
            for candidate in held:
                self.consider(candidate)

    # ── pause ─────────────────────────────────────────────────────────────

    def _pause(self, until: datetime | None) -> None:
        core = self.core
        now = core.clock()
        try:
            with core.db.transaction():
                core.settings.set_paused(now, until)
                result = core.record(
                    EventKind.PAUSED,
                    {"until": until.isoformat() if until else None},
                    now,
                )
        except (SettingNotSaved, EventLogFailed) as error:
            core.bridge.pauseChanged.emit(False, "", "")
            core.bridge.noticeShown.emit(str(error))
            return
        self.paused, self.paused_at, self.paused_until = True, now, until
        for decision_id in list(self._shown):
            self._shown.pop(decision_id)
        core.commit(result)
        self._lapse("paused", now)
        core.bridge.proactiveShown.emit(None)
        core.bridge.pauseChanged.emit(True, _until_text(until, now), "")

    def _resume(self) -> None:
        core = self.core
        now = core.clock()
        began = self.paused_at or now
        try:
            with core.db.transaction():
                core.settings.set_paused(None, None)
                result = core.record(EventKind.RESUMED, {}, now)
        except (SettingNotSaved, EventLogFailed) as error:
            core.bridge.noticeShown.emit(str(error))
            return
        self.paused, self.paused_at, self.paused_until = False, None, None
        core.commit(result)
        minutes = (now - began).total_seconds() / 60
        lasted = speech.duration(minutes) if minutes >= 1 else "less than a minute"
        core.bridge.pauseChanged.emit(False, "", lasted)


def _instruction(candidate: Candidate) -> str:
    question = candidate.factor(speech.QUESTION)
    hint = _HINTS.get(candidate.kind, "").format(
        question=question.text if question else ""
    )
    facts = "\n".join(
        f"- {line}" for line in speech.reasons(candidate.kind, candidate.factors)
    )
    return (
        "You are starting a conversation with the user on your own. Say it in "
        "one or two short sentences, in your own voice. Use only these facts, "
        f"and add no number that is not in them.\n{facts}\n{hint}"
    )


def _until_text(until: datetime | None, now: datetime) -> str:
    if until is None:
        return "until you resume"
    if until.date() != now.date():
        return "until tomorrow"
    return f"until {until:%H:%M}"


def until_for(option: str, now: datetime) -> datetime | None:
    """When a pause of ``hour``, ``today`` or ``off`` ends."""
    if option == "hour":
        return now + timedelta(hours=1)
    if option == "today":
        return day_start(now) + timedelta(days=1)
    return None
