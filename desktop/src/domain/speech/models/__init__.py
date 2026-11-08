"""What the companion may say on its own, and the figures behind each message.

The standard library only. A proactive message never exists without the
factors that explain it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum


class MessageKind(StrEnum):
    """Every kind of message the companion can start. Each can be switched off."""

    BREAK = "break"
    REMARK = "remark"
    QUESTION = "question"
    GREETING = "greeting"
    RETURN = "return"
    ADJUSTMENT = "adjustment"


#: What the user sees for each kind in the settings.
KIND_LABELS: dict[MessageKind, tuple[str, str]] = {
    MessageKind.BREAK: (
        "Break suggestions", "After a long time at the machine"
    ),
    MessageKind.REMARK: (
        "Remarks", "When you have not talked for a while"
    ),
    MessageKind.QUESTION: (
        "Questions to get to know you", "At most one a day"
    ),
    MessageKind.GREETING: (
        "Greeting of the day", "The first time you open Cognia each day"
    ),
    MessageKind.RETURN: (
        "Welcome back", "When you come back after 20 minutes or more"
    ),
    MessageKind.ADJUSTMENT: (
        "Little changes", "When I adjust to suit you (you can undo)"
    ),
}


class Outcome(StrEnum):
    SENT = "sent"
    WITHHELD = "withheld"
    HELD = "held"
    DROPPED = "dropped"


class Response(StrEnum):
    """What the user did with a message that was shown."""

    ANSWERED = "answered"
    DISMISSED = "dismissed"
    PASSED_OVER = "passed_over"
    TAKEN = "taken"
    POSTPONED = "postponed"
    SILENCED = "silenced"


@dataclass(frozen=True)
class Factor:
    """One figure behind a message. ``name`` sets the unit of ``value``:
    seconds for names that end in ``_s``, minutes for ``_min``, a count for
    ``_count``, and a plain number otherwise. ``ref_id`` names a remembered
    line or a pattern, or is empty."""

    name: str
    value: float
    ref_id: str = ""
    event_seq: int | None = None
    text: str = ""


@dataclass(frozen=True)
class Candidate:
    """A wish to speak, with its figures. It is not yet a message."""

    kind: MessageKind
    trigger_seq: int | None
    factors: tuple[Factor, ...]
    created_at: datetime

    def factor(self, name: str) -> Factor | None:
        return next((f for f in self.factors if f.name == name), None)


@dataclass(frozen=True)
class Verdict:
    """What the gate decided. ``withheld_by`` names the rule that stopped a
    message, or is empty."""

    outcome: Outcome | None
    withheld_by: str = ""

    @property
    def passes(self) -> bool:
        return self.outcome is None


@dataclass(frozen=True)
class Moment:
    """What the gate needs to know about now."""

    at: datetime
    at_desk: bool
    locked: bool
    presenting: bool
    typing: bool
    hidden: bool
    sent_today: int


@dataclass(frozen=True)
class SpeechSettings:
    """The user's limits on the companion. ``None`` means no limit."""

    ceiling: int | None
    quiet: tuple[time, time] | None
    enabled: frozenset[MessageKind]
    moods_on: bool
    break_threshold_min: int | None

    @staticmethod
    def defaults() -> SpeechSettings:
        return SpeechSettings(None, None, frozenset(MessageKind), True, None)


@dataclass(frozen=True)
class ProactiveMessage:
    """A message on screen, with the lines that explain it."""

    decision_id: str
    kind: MessageKind
    text: str
    reasons: tuple[str, ...]
    shown_at: datetime
    ref_id: str = ""


@dataclass(frozen=True)
class WordingCheck:
    ok: bool
    problem: str = ""


__all__ = [
    "KIND_LABELS",
    "Candidate",
    "Factor",
    "MessageKind",
    "Moment",
    "Outcome",
    "ProactiveMessage",
    "Response",
    "SpeechSettings",
    "Verdict",
    "WordingCheck",
]
