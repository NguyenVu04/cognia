"""When the companion has a reason to speak first, and when it waits or dozes.

Pure functions over the event log. Time arrives on each event; a wait that
must end later is a timer that the caller fires at :attr:`next_wake`. The
random waits come from ``random.Random(seq)`` of the event that starts them,
so a replay of the same log gives the same waits.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime, timedelta

from src.domain.awareness.rules import BREAK_RESET, day_start
from src.domain.events.models import Event, EventKind
from src.domain.initiative.models import (
    ACTIVE,
    AWAY,
    BREAK,
    DOZE,
    DOZING,
    TALK,
    UNKNOWN,
    Context,
    InitiativeState,
    InitiativeStep,
)
from src.domain.speech import rules as speech
from src.domain.speech.models import Candidate, Factor, MessageKind

DOZE_AFTER = timedelta(minutes=30)
ABSENCE_MIN = timedelta(minutes=20)
T_TALK_MIN = (90, 180)
T_BREAK_MIN = (75, 110)
POSTPONE = timedelta(minutes=20)
# A message on screen this long with no answer, at the desk, was passed over.
PASS_OVER_AFTER = timedelta(minutes=2)
# Before a regular absence, nothing is planned for this long.
ABSENCE_LEAD = timedelta(minutes=30)
# A lively mood speaks sooner and a low one later.
_MOOD_PACE = {"lively": 0.75, "low": 1.25}

_RESPONDED = (EventKind.MESSAGE_ANSWERED, EventKind.MESSAGE_PASSED_OVER)


def t_talk(seq: int, feeling: str, factor: float = 1.0) -> timedelta:
    """How long the companion waits after the last talk before it speaks."""
    minutes = random.Random(seq).uniform(*T_TALK_MIN)
    return timedelta(minutes=minutes * _MOOD_PACE.get(feeling, 1.0) * factor)


def t_break(seq: int, threshold_min: int | None, factor: float = 1.0) -> timedelta:
    """How long at the desk before a break is suggested. The user's threshold
    replaces the random wait."""
    if threshold_min is not None:
        return timedelta(minutes=threshold_min)
    return timedelta(minutes=random.Random(seq).uniform(*T_BREAK_MIN) * factor)


def first_opening(greeted_on: date | None, now: datetime) -> bool:
    """Whether a showing of the window at ``now`` is the first of its day,
    which begins at 04:00."""
    return greeted_on != day_start(now).date()


def _avoid(at: datetime, hours: frozenset[int]) -> datetime:
    """Move a planned time out of the half hour before a regular absence."""
    for hour in hours:
        start = at.replace(hour=hour, minute=0, second=0, microsecond=0)
        if start - ABSENCE_LEAD <= at < start:
            return start
    return at


def _plan(at: datetime, wait: timedelta, ctx: Context) -> datetime:
    return _avoid(at + wait, ctx.learned.absence_hours)


def next_wake(state: InitiativeState) -> datetime | None:
    times = [t for t in (state.talk_at, state.break_at, state.doze_at) if t]
    return min(times) if times else None


def due(state: InitiativeState, now: datetime) -> tuple[str, ...]:
    """The timers that have come due at ``now``."""
    return tuple(
        purpose
        for purpose, at in (
            (TALK, state.talk_at),
            (BREAK, state.break_at),
            (DOZE, state.doze_at),
        )
        if at is not None and at <= now
    )


def _mood(ctx: Context) -> Factor:
    return Factor(speech.MOOD, ctx.arousal, text=ctx.feeling)


def step(state: InitiativeState, event: Event, ctx: Context) -> InitiativeStep:
    """``state`` after ``event``, and what it asks for."""
    result = _apply(state, event, ctx)
    return replace(result, next_wake=next_wake(result.state))


def _apply(state: InitiativeState, event: Event, ctx: Context) -> InitiativeStep:
    at, kind, payload = event.occurred_at, event.kind, event.payload
    if kind == EventKind.PRESENCE:
        if payload.get("stopped"):
            return InitiativeStep(_reset(state), ambient=ACTIVE, lapse="stopped")
        here = bool(payload.get("at_desk")) and not payload.get("locked")
        return _arrive(state, event, ctx) if here else _leave(state, event, True)
    if kind == EventKind.CLOCK_GAP:
        return _leave(state, event, False)
    if kind in (EventKind.PAUSED, EventKind.RESUMED):
        return InitiativeStep(_reset(state), ambient=ACTIVE, lapse="paused")
    if kind in (EventKind.USER_MESSAGE, EventKind.MESSAGE_ANSWERED):
        state = replace(
            state,
            last_talk_seq=event.seq,
            last_talk_at=at,
            talk_at=_plan(
                at,
                t_talk(event.seq, ctx.feeling, _factor(ctx, MessageKind.REMARK)),
                ctx,
            )
            if state.desk == ACTIVE
            else None,
        )
    if kind in _RESPONDED and payload.get("kind") == MessageKind.BREAK.value:
        state = _break_answered(state, event, ctx)
    if kind == EventKind.TIMER:
        return _timers(state, event, ctx)
    return InitiativeStep(state)


def _factor(ctx: Context, kind: MessageKind) -> float:
    return ctx.learned.frequency.get(kind.value, 1.0)


def _reset(state: InitiativeState) -> InitiativeState:
    """Nothing is known about the desk: every timer stops."""
    return replace(
        state,
        desk=UNKNOWN,
        away_since=None,
        talk_at=None,
        break_at=None,
        doze_at=None,
        run_start_at=None,
        run_start_seq=None,
    )


def _leave(state: InitiativeState, event: Event, trusted: bool) -> InitiativeStep:
    if state.desk in (AWAY, DOZING):
        if not trusted:
            state = replace(state, away_trusted=False)
        return InitiativeStep(state)
    idle = float(event.payload.get("idle_seconds", 0) or 0)
    since = (
        event.occurred_at - timedelta(seconds=idle) if trusted else event.occurred_at
    )
    state = replace(
        state,
        desk=AWAY,
        away_since=since,
        away_trusted=trusted,
        doze_at=since + DOZE_AFTER,
        talk_at=None,
        break_at=None,
    )
    return InitiativeStep(state, ambient="waiting", lapse="away")


def _arrive(state: InitiativeState, event: Event, ctx: Context) -> InitiativeStep:
    if state.desk == ACTIVE:
        return InitiativeStep(state)
    at = event.occurred_at
    candidates: tuple[Candidate, ...] = ()
    away = at - state.away_since if state.away_since is not None else None
    if away is not None and away >= ABSENCE_MIN:
        factor = (
            Factor(speech.AWAY_MIN, round(away.total_seconds() / 60))
            if state.away_trusted
            else Factor(speech.AWAY_UNKNOWN, 0.0)
        )
        candidates = (
            Candidate(MessageKind.RETURN, event.seq, (factor, _mood(ctx)), at),
        )
    new_run = (
        away is None
        or away >= timedelta(seconds=BREAK_RESET)
        or (state.run_start_at is None)
    )
    if new_run:
        wait = t_break(event.seq, ctx.threshold_min, _factor(ctx, MessageKind.BREAK))
        state = replace(
            state,
            run_start_seq=event.seq,
            run_start_at=at,
            threshold_s=wait.total_seconds(),
            threshold_chosen=ctx.threshold_min is None,
            break_at=_plan(at, wait, ctx),
            postponed_breaks=0,
        )
    elif state.run_start_at is not None and state.break_at is None:
        state = replace(state, break_at=_plan(at, POSTPONE, ctx))
    talk_from = state.last_talk_at if state.last_talk_at else at
    talk_seq = state.last_talk_seq if state.last_talk_seq is not None else event.seq
    talk_at = _plan(
        talk_from, t_talk(talk_seq, ctx.feeling, _factor(ctx, MessageKind.REMARK)), ctx
    )
    state = replace(
        state,
        desk=ACTIVE,
        away_since=None,
        away_trusted=True,
        doze_at=None,
        talk_at=max(talk_at, at + timedelta(minutes=1)),
    )
    return InitiativeStep(state, candidates, ambient=ACTIVE)


def _break_answered(
    state: InitiativeState, event: Event, ctx: Context
) -> InitiativeState:
    response = event.payload.get("response")
    at = event.occurred_at
    if response == "silenced":
        return replace(state, silenced_on=day_start(at).date(), break_at=None)
    if response in ("postponed", "passed_over"):
        return replace(
            state,
            break_at=_plan(at, POSTPONE, ctx),
            postponed_breaks=state.postponed_breaks + 1,
        )
    return replace(state, postponed_breaks=0, break_at=None)


def _timers(state: InitiativeState, event: Event, ctx: Context) -> InitiativeStep:
    at = event.occurred_at
    purposes = event.payload.get("purposes") or ()
    candidates: list[Candidate] = []
    ambient = ""
    if DOZE in purposes and state.desk == AWAY:
        state = replace(state, desk=DOZING, doze_at=None)
        ambient = DOZING
    if BREAK in purposes and state.desk == ACTIVE and state.run_start_at:
        state = replace(state, break_at=None)
        if state.silenced_on != day_start(at).date():
            candidates.append(_break(state, event, ctx))
    if TALK in purposes and state.desk == ACTIVE:
        state, talk = _talk(state, event, ctx)
        candidates.append(talk)
    return InitiativeStep(state, tuple(candidates), ambient=ambient)


def _break(state: InitiativeState, event: Event, ctx: Context) -> Candidate:
    observed = (event.occurred_at - state.run_start_at).total_seconds()
    factors = [
        Factor(speech.OBSERVED_S, observed, event_seq=state.run_start_seq),
        Factor(
            speech.THRESHOLD_S,
            state.threshold_s,
            text="chosen" if state.threshold_chosen else "user",
        ),
        _mood(ctx),
    ]
    if state.postponed_breaks >= 3:
        factors.append(Factor("postponed_count", float(state.postponed_breaks)))
    return Candidate(MessageKind.BREAK, event.seq, tuple(factors), event.occurred_at)


def _talk(
    state: InitiativeState, event: Event, ctx: Context
) -> tuple[InitiativeState, Candidate]:
    at = event.occurred_at
    since = state.last_talk_at or state.run_start_at or at
    quiet = Factor(
        speech.QUIET_MIN,
        round((at - since).total_seconds() / 60),
        event_seq=state.last_talk_seq,
    )
    state = replace(state, talk_at=None)
    question = next_question(state, ctx.questions, at)
    if question is not None:
        question_id, text = question
        state = replace(
            state,
            asked=state.asked | {question_id},
            last_question_on=day_start(at).date(),
        )
        factors = (
            quiet,
            Factor(speech.QUESTION, 1.0, ref_id=question_id, text=text),
            _mood(ctx),
        )
        return state, Candidate(MessageKind.QUESTION, event.seq, factors, at)
    return state, Candidate(MessageKind.REMARK, event.seq, (quiet, _mood(ctx)), at)


def next_question(
    state: InitiativeState, questions: Sequence[tuple[str, str]], now: datetime
) -> tuple[str, str] | None:
    """The next question not yet asked, at most one a day."""
    if state.last_question_on == day_start(now).date():
        return None
    return next(
        ((qid, text) for qid, text in questions if qid not in state.asked), None
    )


def greeting(
    state: InitiativeState,
    event: Event,
    told: tuple[str, str] | None,
    ctx: Context,
) -> tuple[InitiativeState, Candidate | None]:
    """The greeting of the first opening of the day, mentioning ``told``, the
    latest line the user told on the last day they talked, as (id, text)."""
    if not first_opening(state.greeted_on, event.occurred_at):
        return state, None
    state = replace(state, greeted_on=day_start(event.occurred_at).date())
    item = (
        Factor(speech.TOLD_LINE, 1.0, ref_id=told[0], text=told[1])
        if told
        else Factor(speech.NOTHING, 0.0)
    )
    candidate = Candidate(
        MessageKind.GREETING, event.seq, (item, _mood(ctx)), event.occurred_at
    )
    return state, candidate


def at_desk_now(state: InitiativeState) -> bool:
    """Whether a message may count the user as present. With desk awareness
    off nothing is known, so a message the user's own action starts may show."""
    return state.desk in (ACTIVE, UNKNOWN)


__all__ = [
    "ABSENCE_MIN",
    "DOZE_AFTER",
    "PASS_OVER_AFTER",
    "at_desk_now",
    "due",
    "first_opening",
    "greeting",
    "next_question",
    "next_wake",
    "step",
    "t_break",
    "t_talk",
]
