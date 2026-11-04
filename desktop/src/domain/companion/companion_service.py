"""The companion's state, folded from the event log and moved by each new event."""

from __future__ import annotations

from datetime import datetime

from src.domain.companion import rules
from src.domain.companion.models import CompanionState, StepResult
from src.domain.emotion.emotion_service import EmotionService
from src.domain.events.models import EventKind, Payload
from src.domain.ports import EventLog


class CompanionService:
    """Records each event and applies the rules to it.

    It holds no state: the caller keeps the :class:`CompanionState` between
    events and hands it back. Exceptions from the ports pass through unchanged.
    """

    def __init__(self, log: EventLog, emotion: EmotionService) -> None:
        self._log = log
        self._emotion = emotion

    def start(self) -> CompanionState:
        """The state after every event in the log."""
        return rules.fold(
            rules.initial_state(), self._log.read_from(1), self._emotion.temperaments()
        )

    def record(
        self,
        state: CompanionState,
        occurred_at: datetime,
        utc_offset_min: int,
        kind: EventKind,
        payload: Payload,
        importance: int | None,
    ) -> StepResult:
        """Record one event and apply it to ``state``.

        Raises ``ValueError`` if the event names an unknown character version.
        """
        # Read first, so that a failed read records nothing.
        temperaments = self._emotion.temperaments()
        event = self._log.append(occurred_at, utc_offset_min, kind, payload, importance)
        return rules.step(state, event, temperaments)
