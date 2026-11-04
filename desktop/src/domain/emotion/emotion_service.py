"""How each version of the character feels things."""

from __future__ import annotations

from src.domain.emotion.models import Temperament
from src.domain.ports import CharacterStore


class EmotionService:
    """Reads the temperament of each character version for the rules.

    It holds no state. Exceptions from the store pass through unchanged.
    """

    def __init__(self, store: CharacterStore) -> None:
        self._store = store

    def temperaments(self) -> dict[str, Temperament]:
        """The temperament of every version, by version ID. Empty until the
        first choice."""
        return {version.id: version.temperament for version in self._store.versions()}
