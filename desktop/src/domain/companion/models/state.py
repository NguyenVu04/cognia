"""Everything the rules hold between two events, and the result of one step.

No table holds this state. It is a pure function of the event log, so the core
thread computes it again from the log at each start.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.companion.models.effects import Effect
from src.domain.emotion.models import EmotionState, Pad, Temperament
from src.domain.events.models import Event


@dataclass(frozen=True)
class CompanionState:
    """``version_id`` is the character version in force, and ``emotion`` its
    feelings. Both are ``None`` until the first ``character_changed``."""

    version_id: str | None
    moods_on: bool
    emotion: EmotionState | None


@dataclass(frozen=True)
class StepResult:
    """The state after one event, what to do outside, the next time the rules
    want to run, and the event itself. ``next_wake`` is ``None`` if no rule
    needs a wake."""

    state: CompanionState
    effects: tuple[Effect, ...]
    next_wake: datetime | None
    event: Event | None = None


@dataclass(frozen=True)
class Cause:
    """One recorded event that moved the feeling, and how far. For a message,
    ``interpretation`` is how the model read it, with its confidence."""

    when: str
    what: str
    push: Pad
    interpretation: str = ""

    def text(self) -> str:
        return (
            f"{self.when}, {self.what}: pleasure {self.push.pleasure:+.2f}, "
            f"arousal {self.push.arousal:+.2f}"
        )


@dataclass(frozen=True)
class FeelingExplanation:
    """Why the companion feels as it does, from the recorded figures only."""

    feeling: str
    point: Pad
    rest: str
    temperament: Temperament
    causes: tuple[Cause, ...]
    floor_reached: bool
