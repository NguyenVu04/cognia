"""How a character feels things: how far events move it, how fast feelings fade,
and where its mood comes to rest.

The author sets these values by hand for each ready-made character, and they
never change within one version.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.emotion.models.pad import Pad


@dataclass(frozen=True)
class Temperament:
    """Raises ``ValueError`` for a value the stored version would refuse."""

    reactivity: float
    feeling_half_life_min: float
    mood_half_life_min: float
    rest: Pad

    def __post_init__(self) -> None:
        if not 0 <= self.reactivity <= 1:
            raise ValueError(f"reactivity must be 0 to 1, not {self.reactivity}")
        if self.feeling_half_life_min <= 0:
            raise ValueError("feeling_half_life_min must be greater than 0")
        if self.mood_half_life_min <= 0:
            raise ValueError("mood_half_life_min must be greater than 0")
        for axis in (self.rest.pleasure, self.rest.arousal, self.rest.dominance):
            if not -1 <= axis <= 1:
                raise ValueError(f"each axis of rest must be -1 to 1, not {axis}")
