"""Everything the rules hold between two events, and the result of one step.

No table holds this state. It is a pure function of the event log, so the core
thread computes it again from the log at each start.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.companion.models.effects import Effect
from src.domain.emotion.models import EmotionState


@dataclass(frozen=True)
class CompanionState:
    """``version_id`` is the character version in force, and ``emotion`` its
    feelings. Both are ``None`` until the first ``character_changed``."""

    version_id: str | None
    moods_on: bool
    emotion: EmotionState | None


@dataclass(frozen=True)
class StepResult:
    """The state after one event, what to do outside, and the next time the
    rules want to run. ``next_wake`` is ``None`` if no rule needs a wake."""

    state: CompanionState
    effects: tuple[Effect, ...]
    next_wake: datetime | None
