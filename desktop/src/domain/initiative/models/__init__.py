"""What the initiative rules hold between two events.

The standard library only. Like the feeling, this state is a pure function of
the event log, so a replay of the log gives the same state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from src.domain.speech.models import Candidate

ACTIVE = "active"
AWAY = "away"
DOZING = "dozing"
# Desk awareness is off or paused: nothing is known about the desk.
UNKNOWN = "unknown"

TALK = "talk"
BREAK = "break"
DOZE = "doze"


@dataclass(frozen=True)
class Learned:
    """What learning changed in the timing: a factor on the wait of each kind,
    and hours of the day before which nothing is planned."""

    frequency: dict[str, float] = field(default_factory=dict)
    absence_hours: frozenset[int] = frozenset()


@dataclass(frozen=True)
class Context:
    """What the rules read besides the event: the feeling now, the user's
    break threshold, what learning changed, and the questions not asked yet."""

    feeling: str
    arousal: float
    threshold_min: int | None
    learned: Learned
    questions: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class InitiativeState:
    desk: str = UNKNOWN
    run_start_seq: int | None = None
    run_start_at: datetime | None = None
    threshold_s: float = 0.0
    threshold_chosen: bool = True
    away_since: datetime | None = None
    away_trusted: bool = True
    last_talk_seq: int | None = None
    last_talk_at: datetime | None = None
    talk_at: datetime | None = None
    break_at: datetime | None = None
    doze_at: datetime | None = None
    postponed_breaks: int = 0
    silenced_on: date | None = None
    asked: frozenset[str] = frozenset()
    last_question_on: date | None = None
    greeted_on: date | None = None


@dataclass(frozen=True)
class InitiativeStep:
    """The state after one event, the messages it wants to say, the ambient
    state to show (or ""), whether waiting messages lapse, and the next time
    the rules want to run."""

    state: InitiativeState
    candidates: tuple[Candidate, ...] = ()
    ambient: str = ""
    lapse: str = ""
    next_wake: datetime | None = None


__all__ = [
    "ACTIVE",
    "AWAY",
    "BREAK",
    "DOZE",
    "DOZING",
    "TALK",
    "UNKNOWN",
    "Context",
    "InitiativeState",
    "InitiativeStep",
    "Learned",
]
