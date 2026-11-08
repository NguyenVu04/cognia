"""The gate that every message the companion starts must pass.

Pure functions. A message passes only if the moment allows it, the user's
limits allow it, and every figure that explains it is present. Its words are
checked: each number must come from the figures, and wording that blames or
pressures the user is refused.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import time

from src.domain.speech.models import (
    Candidate,
    Factor,
    MessageKind,
    Moment,
    Outcome,
    SpeechSettings,
    Verdict,
    WordingCheck,
)

# Factor names. A name ending in _s holds seconds, in _min minutes.
OBSERVED_S = "observed_s"
THRESHOLD_S = "threshold_s"
TYPING_DELAY_S = "typing_delay_s"
MOOD = "mood"
CEILING = "ceiling"
QUIET_MIN = "quiet_min"
QUESTION = "question"
TOLD_LINE = "told_line"
NOTHING = "nothing"
AWAY_MIN = "away_min"
AWAY_UNKNOWN = "away_unknown"
PATTERN = "pattern"
ADJUSTMENT = "adjustment"

# The rule that stopped a message, as it is recorded.
LOCKED = "locked"
PRESENTING = "presenting"
QUIET_HOURS = "quiet_hours"
KIND_OFF = "kind_off"
CEILING_REACHED = "ceiling"
AWAY = "away"
DEFECT = "defect"
HIDDEN = "hidden"
NO_WORDS = "no_words"

_REQUIRED: dict[MessageKind, frozenset[str]] = {
    MessageKind.BREAK: frozenset({OBSERVED_S, THRESHOLD_S, MOOD, CEILING}),
    MessageKind.REMARK: frozenset({QUIET_MIN, MOOD, CEILING}),
    MessageKind.QUESTION: frozenset({QUIET_MIN, QUESTION, MOOD, CEILING}),
    MessageKind.GREETING: frozenset({MOOD}),
    MessageKind.RETURN: frozenset({MOOD}),
    MessageKind.ADJUSTMENT: frozenset({PATTERN, ADJUSTMENT}),
}
# One of these must be present for the kind as well.
_ONE_OF: dict[MessageKind, frozenset[str]] = {
    MessageKind.GREETING: frozenset({TOLD_LINE, NOTHING}),
    MessageKind.RETURN: frozenset({AWAY_MIN, AWAY_UNKNOWN}),
}
# Wording that blames, pressures or claims to know what the user does.
FORBIDDEN = ("working", "behind", "where have you been", "you never", "you should")
_NUMBER = re.compile(r"\d+")


def required_factors(kind: MessageKind) -> frozenset[str]:
    return _REQUIRED[kind]


def missing(candidate: Candidate) -> tuple[str, ...]:
    """The figures the candidate lacks; empty when it can be explained."""
    names = {f.name for f in candidate.factors}
    lacking = sorted(_REQUIRED[candidate.kind] - names)
    one_of = _ONE_OF.get(candidate.kind)
    if one_of and not names & one_of:
        lacking.append("|".join(sorted(one_of)))
    return tuple(lacking)


def in_quiet_hours(at: time, quiet: tuple[time, time] | None) -> bool:
    """Whether ``at`` falls in quiet hours that may run past midnight."""
    if quiet is None:
        return False
    start, end = quiet
    if start <= end:
        return start <= at < end
    return at >= start or at < end


def admit(candidate: Candidate, moment: Moment, settings: SpeechSettings) -> Verdict:
    """Whether the candidate may be said now. A verdict that passes has no
    outcome; the caller then waits for a pause in typing."""
    if moment.locked:
        return Verdict(Outcome.WITHHELD, LOCKED)
    if moment.presenting:
        return Verdict(Outcome.WITHHELD, PRESENTING)
    if in_quiet_hours(moment.at.timetz().replace(tzinfo=None), settings.quiet):
        return Verdict(Outcome.WITHHELD, QUIET_HOURS)
    if candidate.kind not in settings.enabled:
        return Verdict(Outcome.WITHHELD, KIND_OFF)
    counts = candidate.kind is not MessageKind.GREETING
    if (
        counts
        and settings.ceiling is not None
        and moment.sent_today >= settings.ceiling
    ):
        return Verdict(Outcome.WITHHELD, CEILING_REACHED)
    if not moment.at_desk:
        return Verdict(Outcome.WITHHELD, AWAY)
    if lacking := missing(candidate):
        return Verdict(Outcome.WITHHELD, f"{DEFECT}:{','.join(lacking)}")
    if moment.hidden:
        return Verdict(Outcome.HELD, HIDDEN)
    return Verdict(None)


def ceiling_factor(settings: SpeechSettings, sent_today: int) -> Factor:
    """The ceiling and how much of it is used; -1 means none."""
    limit = -1 if settings.ceiling is None else settings.ceiling
    return Factor(CEILING, float(limit), text=str(sent_today))


def allowed_numbers(factors: Sequence[Factor]) -> set[int]:
    """Every number a message may state: each figure, in the units it is
    shown in."""
    allowed: set[int] = set()
    for factor in factors:
        value = factor.value
        if factor.name.endswith("_s"):
            value = value / 60
        minutes = round(value)
        allowed.add(minutes)
        if factor.name.endswith(("_s", "_min")):
            hours, rest = divmod(minutes, 60)
            allowed.update({hours, rest})
        if factor.name == CEILING and factor.text.isdigit():
            allowed.add(int(factor.text))
        allowed.update(int(n) for n in _NUMBER.findall(factor.text))
    return allowed


def check_wording(text: str, factors: Sequence[Factor]) -> WordingCheck:
    """Whether the words state only the figures and avoid blame."""
    lowered = text.lower()
    for phrase in FORBIDDEN:
        if phrase in lowered:
            return WordingCheck(False, f"uses “{phrase}”")
    if not text.strip():
        return WordingCheck(False, "has no words")
    allowed = allowed_numbers(factors)
    for number in _NUMBER.findall(text):
        if int(number) not in allowed:
            return WordingCheck(False, f"states {number}, which no figure gives")
    return WordingCheck(True)


def duration(minutes: float) -> str:
    """For example "45 minutes" or "2 hours 47 minutes"."""
    total = max(0, round(minutes))
    hours, rest = divmod(total, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if rest or not hours:
        parts.append(f"{rest} minute{'s' if rest != 1 else ''}")
    return " ".join(parts)


def _get(factors: Sequence[Factor], name: str) -> Factor | None:
    return next((f for f in factors if f.name == name), None)


def fixed_wording(kind: MessageKind, factors: Sequence[Factor]) -> str | None:
    """Plain words for the kinds that may be said without the model. ``None``
    for a kind that is not said without it."""
    match kind:
        case MessageKind.BREAK:
            observed = _get(factors, OBSERVED_S)
            if observed is None:
                return None
            return (
                f"You've been at the machine for {duration(observed.value / 60)}. "
                "Time for a short break?"
            )
        case MessageKind.GREETING:
            told = _get(factors, TOLD_LINE)
            if told is not None:
                return f"Good to see you. Last time you told me: “{told.text}”"
            return "Good to see you. Nothing needs your attention."
        case MessageKind.RETURN:
            away = _get(factors, AWAY_MIN)
            if away is not None:
                return f"Welcome back. I waited about {duration(away.value)}."
            return "Welcome back. I can't tell how long you were away."
        case MessageKind.ADJUSTMENT:
            pattern = _get(factors, PATTERN)
            change = _get(factors, ADJUSTMENT)
            if pattern is None or change is None:
                return None
            return f"{pattern.text} So I changed {change.text}. You can undo it."
    return None


def reasons(kind: MessageKind, factors: Sequence[Factor]) -> tuple[str, ...]:
    """Why the message appeared, from its figures, one line each."""
    lines = []
    for factor in factors:
        if line := _reason(kind, factor):
            lines.append(line)
    return tuple(lines)


def _reason(kind: MessageKind, factor: Factor) -> str:
    match factor.name:
        case "observed_s":
            return (
                f"You've been here without a break for {duration(factor.value / 60)}."
            )
        case "threshold_s":
            whose = (
                "Your break threshold"
                if factor.text == "user"
                else ("The break threshold I chose")
            )
            return f"{whose}: {duration(factor.value / 60)}."
        case "typing_delay_s":
            if factor.value < 1:
                return "You weren't typing, so I said it right away."
            return f"I waited {duration(factor.value / 60)} for you to stop typing."
        case "mood":
            effect = {
                "lively": "so I spoke sooner",
                "low": "so I waited longer",
            }.get(factor.text, "which did not change the timing")
            return f"My mood: {factor.text}, {effect}."
        case "ceiling":
            if factor.value < 0:
                return "You haven't set a daily limit."
            return f"I've started {factor.text} of my {int(factor.value)} chats today."
        case "quiet_min":
            return f"We had not talked for {duration(factor.value)}."
        case "question":
            return "A question to get to know you. I ask at most one a day."
        case "told_line":
            return f"The latest thing you told me: “{factor.text}”."
        case "nothing":
            return "Nothing needs your attention."
        case "away_min":
            return f"You were away for {duration(factor.value)}."
        case "away_unknown":
            return (
                "The computer slept or the clock changed, so I can't tell for how long."
            )
        case "pattern":
            return (
                f"What I noticed: {factor.text} ({int(factor.value)} recorded events)."
            )
        case "adjustment":
            return f"What I changed: {factor.text}."
        case "postponed_count":
            return (
                f"You've put off the last {int(factor.value)} breaks. Maybe a "
                "different threshold would suit you better."
            )
    return ""
