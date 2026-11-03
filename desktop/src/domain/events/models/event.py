"""One recorded fact about what happened, from a closed set of kinds.

An event holds references and figures, never the user's words. Its time is the
only clock a rule sees, so the same events always give the same result.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

Payload = Mapping[str, str | int | float | bool]


class EventKind(StrEnum):
    """Every kind of event. A new kind is a change here, not a new string."""

    USER_MESSAGE = "user_message"
    MESSAGE_RATED = "message_rated"
    PRESENCE = "presence"
    TYPING_PAUSE = "typing_pause"
    FOREGROUND_APP = "foreground_app"
    APP_HOUR_CLOSED = "app_hour_closed"
    CLOCK_GAP = "clock_gap"
    TIMER = "timer"
    WINDOW_OPENED = "window_opened"
    SESSION_OPENED = "session_opened"
    INTENT_CHANGED = "intent_changed"
    SESSION_CLOSED = "session_closed"
    MESSAGE_SHOWN = "message_shown"
    MESSAGE_ANSWERED = "message_answered"
    MESSAGE_PASSED_OVER = "message_passed_over"
    MEMORY_STORED = "memory_stored"
    MEMORY_REMOVED = "memory_removed"
    COMMITMENT_ADDED = "commitment_added"
    COMMITMENT_CLOSED = "commitment_closed"
    PATTERN_FOUND = "pattern_found"
    ADJUSTMENT_APPLIED = "adjustment_applied"
    ADJUSTMENT_UNDONE = "adjustment_undone"
    PROPOSAL_DECIDED = "proposal_decided"
    PATTERN_REJECTED = "pattern_rejected"
    REFLECTION_WRITTEN = "reflection_written"
    REFLECTION_DELETED = "reflection_deleted"
    PAUSED = "paused"
    RESUMED = "resumed"
    SETTING_CHANGED = "setting_changed"
    CHARACTER_CHANGED = "character_changed"


class MessageClass(StrEnum):
    """What the AI model found a user message to be. A message it cannot place
    in this set with confidence raises no event."""

    PRAISE = "praise"
    COMPLAINT = "complaint"
    GOOD_NEWS = "good_news"
    BAD_NEWS = "bad_news"
    SHARED_WORRY = "shared_worry"
    NOTHING = "nothing"


@dataclass(frozen=True)
class Event:
    """One row of the event log.

    The payload keys the feelings read: ``class`` on ``user_message``, a
    :class:`MessageClass` value; ``at_desk`` on ``message_answered`` and
    ``message_passed_over``; ``finished`` on ``commitment_closed``.

    Raises ``ValueError`` for a value the stored event would refuse.
    """

    seq: int
    occurred_at: datetime
    utc_offset_min: int
    kind: EventKind
    payload: Payload
    importance: int | None

    def __post_init__(self) -> None:
        if self.seq < 1:
            raise ValueError(f"seq must be 1 or more, not {self.seq}")
        if self.importance is not None and not 1 <= self.importance <= 10:
            raise ValueError(f"importance must be 1 to 10, not {self.importance}")
