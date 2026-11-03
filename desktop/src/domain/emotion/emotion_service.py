"""The companion's feelings under the temperament of the character in force."""

from __future__ import annotations

from datetime import datetime

from src.domain.emotion import rules
from src.domain.emotion.models import EmotionState, Temperament
from src.domain.events.models import Event
from src.domain.ports import CharacterStore


class EmotionService:
    """Reads the temperament of the version in force and applies the rules.

    It holds no state: the caller keeps the :class:`EmotionState` between
    events and hands it back. Exceptions from the store pass through unchanged.
    """

    def __init__(self, store: CharacterStore) -> None:
        self._store = store

    def resting(self, at: datetime, seq: int = 0) -> EmotionState | None:
        """The state at the resting mood, or ``None`` until the first choice."""
        version = self._store.current()
        if version is None:
            return None
        return rules.at_rest(version.temperament, at, seq)

    def feel(
        self, state: EmotionState, event: Event, moods_on: bool = True
    ) -> EmotionState:
        """``state`` after ``event``. With moods off it stays at the resting mood.

        Raises ``ValueError`` if no character is in force.
        """
        temperament = self._temperament()
        if not moods_on:
            return rules.at_rest(temperament, event.occurred_at, event.seq)
        return rules.feel(state, event, temperament)

    def _temperament(self) -> Temperament:
        version = self._store.current()
        if version is None:
            raise ValueError("No character is in force, so nothing can be felt.")
        return version.temperament
