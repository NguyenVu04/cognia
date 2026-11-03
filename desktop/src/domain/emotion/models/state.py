"""The companion's emotion state: a mood that lasts for hours or days, and a
feeling from the latest events that fades in minutes.

No table holds this state. The core thread keeps it in memory and computes it
again from the event log at each start.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.emotion.models.pad import Pad


@dataclass(frozen=True)
class EmotionState:
    """``computed_to_seq`` and ``computed_at`` are the last event applied, or
    0 and the start time before any. ``ignored_loss`` is the pleasure that the
    mood lost to being ignored and has not yet got back. ``floor_reached`` is
    true if the floor on sadness stopped the last event."""

    mood: Pad
    feeling: Pad
    computed_to_seq: int
    computed_at: datetime
    ignored_loss: float = 0.0
    floor_reached: bool = False

    def shown(self) -> Pad:
        """The point the user sees: the mood plus the feeling, each axis -1 to 1."""
        return Pad(
            _limit(self.mood.pleasure + self.feeling.pleasure),
            _limit(self.mood.arousal + self.feeling.arousal),
            _limit(self.mood.dominance + self.feeling.dominance),
        )


def _limit(axis: float) -> float:
    return max(-1.0, min(1.0, axis))
