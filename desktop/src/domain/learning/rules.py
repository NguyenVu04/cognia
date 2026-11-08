"""How the companion learns from what it observed.

Pure functions. The rules count events and find a pattern only when the counts
show it; the pattern then changes one thing about the companion. Three rules:

* ``passed_over_kind``: three messages of one kind passed over in a row while
  the user was at the desk. That kind then waits half as long again.
* ``regular_absence``: an absence of 20 minutes or more that began in the same
  hour on three of the last seven days. Nothing is planned in the half hour
  before that hour.
* ``short_messages``: the user's last twenty messages are short. Replies get
  shorter too.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import replace
from datetime import date, timedelta
from statistics import median

from src.domain.events.models import Event, EventKind
from src.domain.learning.models import (
    FREQUENCY,
    LENGTH,
    PASSED_OVER_KIND,
    REGULAR_ABSENCE,
    SHORT_MESSAGES,
    TIMING,
    Adjustment,
    LearningState,
    Pattern,
)

PASSED_OVER_STREAK = 3
FREQUENCY_FACTOR = 1.5
ABSENCE_DAYS = 3
ABSENCE_WINDOW_DAYS = 7
ABSENCE_MIN = timedelta(minutes=20)
SHORT_SAMPLE = 20
SHORT_MEDIAN_CHARS = 40

_KIND_WORDS = {
    "break": "break suggestions",
    "remark": "remarks",
    "question": "questions",
    "return": "welcomes back",
    "greeting": "greetings",
    "adjustment": "notes about changes",
}


def observe(state: LearningState, event: Event) -> LearningState:
    """``state`` with ``event`` counted. Only small totals and the seqs behind
    them are kept, never the events themselves."""
    kind, payload = event.kind, event.payload
    if kind == EventKind.MESSAGE_PASSED_OVER and payload.get("at_desk"):
        message = str(payload.get("kind", ""))
        streak = (*state.passed.get(message, ()), event.seq)[-PASSED_OVER_STREAK:]
        return replace(state, passed={**state.passed, message: streak})
    if kind == EventKind.MESSAGE_ANSWERED:
        message = str(payload.get("kind", ""))
        return replace(state, passed={**state.passed, message: ()})
    if kind == EventKind.PRESENCE and not payload.get("stopped"):
        return _presence(state, event)
    if kind == EventKind.USER_MESSAGE and isinstance(payload.get("chars"), int):
        lengths = (*state.lengths, (payload["chars"], event.seq))[-SHORT_SAMPLE:]
        return replace(state, lengths=lengths)
    return state


def _presence(state: LearningState, event: Event) -> LearningState:
    here = bool(event.payload.get("at_desk")) and not event.payload.get("locked")
    if not here:
        if state.leaving is None:
            idle = float(event.payload.get("idle_seconds", 0) or 0)
            return replace(state, leaving=(event.occurred_at - timedelta(seconds=idle),
                                           event.seq))
        return state
    if state.leaving is None:
        return state
    began, seq = state.leaving
    state = replace(state, leaving=None)
    if event.occurred_at - began < ABSENCE_MIN:
        return state
    hour = began.hour
    day = began.date().isoformat()
    kept = tuple(
        (d, s) for d, s in state.absences.get(hour, ())
        if d != day and began.date() - _date(d) < timedelta(days=ABSENCE_WINDOW_DAYS)
    )
    return replace(state, absences={**state.absences, hour: (*kept, (day, seq))})


def _date(text: str) -> date:
    return date.fromisoformat(text)


def find_patterns(
    state: LearningState,
    known: Collection[str],
    rejected: Collection[tuple[str, tuple[int, ...]]],
) -> tuple[Pattern, ...]:
    """The patterns the counts show now, without those already ``known`` by
    fingerprint and without one the user marked wrong on the same evidence."""
    found: list[Pattern] = []
    for kind, seqs in state.passed.items():
        if len(seqs) >= PASSED_OVER_STREAK:
            found.append(_pattern(PASSED_OVER_KIND, (("kind", kind),), seqs))
    for hour, days in state.absences.items():
        if len(days) >= ABSENCE_DAYS:
            found.append(_pattern(
                REGULAR_ABSENCE, (("hour", str(hour)),), tuple(s for _, s in days)
            ))
    if len(state.lengths) >= SHORT_SAMPLE:
        if median(n for n, _ in state.lengths) < SHORT_MEDIAN_CHARS:
            found.append(_pattern(
                SHORT_MESSAGES, (), tuple(s for _, s in state.lengths)
            ))
    tombstones = set(rejected)
    return tuple(
        p for p in found
        if p.fingerprint not in known and (p.fingerprint, p.evidence) not in tombstones
    )


def _pattern(rule_id: str, parameters, evidence) -> Pattern:
    draft = Pattern(rule_id, tuple(parameters), tuple(evidence), "")
    return replace(draft, statement=statement(draft))


def statement(pattern: Pattern) -> str:
    """The plain sentence the user sees for a pattern."""
    match pattern.rule_id:
        case "passed_over_kind":
            words = _KIND_WORDS.get(pattern.parameter("kind"), "messages")
            return f"You let my last {len(pattern.evidence)} {words} pass."
        case "regular_absence":
            return (
                f"You often step away around {int(pattern.parameter('hour')):02d}:00."
            )
        case "short_messages":
            return "You like to keep your messages short."
    return ""


def adjustments_for(pattern: Pattern) -> tuple[Adjustment, ...]:
    """What the pattern changes. Nothing else changes without the user."""
    match pattern.rule_id:
        case "passed_over_kind":
            return (Adjustment(FREQUENCY, "1.0", str(FREQUENCY_FACTOR)),)
        case "regular_absence":
            return (Adjustment(TIMING, "", pattern.parameter("hour")),)
        case "short_messages":
            return (Adjustment(LENGTH, "usual", "short"),)
    return ()


def describe(pattern: Pattern) -> str:
    """What the pattern changed, in plain words."""
    match pattern.rule_id:
        case "passed_over_kind":
            words = _KIND_WORDS.get(pattern.parameter("kind"), "messages")
            return f"I'll send {words} less often"
        case "regular_absence":
            hour = int(pattern.parameter("hour"))
            return f"I won't start a chat in the half hour before {hour:02d}:00"
        case "short_messages":
            return "I'll keep my replies shorter"
    return ""


def frequency(patterns: Iterable[Pattern]) -> dict[str, float]:
    """The factor on the wait of each kind that learning slowed down."""
    return {
        p.parameter("kind"): FREQUENCY_FACTOR
        for p in patterns if p.rule_id == PASSED_OVER_KIND
    }


def absence_hours(patterns: Iterable[Pattern]) -> frozenset[int]:
    return frozenset(
        int(p.parameter("hour")) for p in patterns if p.rule_id == REGULAR_ABSENCE
    )


def wants_short_replies(patterns: Iterable[Pattern]) -> bool:
    return any(p.rule_id == SHORT_MESSAGES for p in patterns)
