"""The companion's state, folded from the event log and moved by each new event."""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo

from src.domain.companion import rules
from src.domain.companion.models import (
    CompanionState,
    FeelingExplanation,
    StepResult,
)
from src.domain.emotion.emotion_service import EmotionService
from src.domain.emotion.models import Pad
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

    def temperaments(self):
        """The temperament of each character version, by its id."""
        return self._emotion.temperaments()

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

    def why(self, state: CompanionState, at: datetime, zone: tzinfo) -> str:
        """The feeling at ``at`` and the recorded events that moved it. Raises
        ``ValueError`` with no character."""
        since = at - timedelta(days=rules.CAUSE_DAYS)
        return rules.explain_feeling(
            state, self._log.read_since(since), self._emotion.temperaments(), at, zone
        )

    def explanation(
        self, state: CompanionState, at: datetime, zone: tzinfo
    ) -> FeelingExplanation | None:
        """The feeling at ``at`` and what moved it, as figures. ``None`` with
        moods off. Raises ``ValueError`` with no character."""
        since = at - timedelta(days=rules.CAUSE_DAYS)
        return rules.feeling_explanation(
            state, self._log.read_since(since), self._emotion.temperaments(), at, zone
        )

    def shown_at(self, state: CompanionState, at: datetime) -> Pad | None:
        """The point the user sees at ``at``. ``None`` with no character."""
        return rules.shown_at(state, at, self._emotion.temperaments())
