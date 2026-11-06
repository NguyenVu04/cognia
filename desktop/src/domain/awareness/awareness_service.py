"""Time at the machine and in each application, read from the event log."""

from __future__ import annotations

from datetime import datetime, timedelta

from src.domain.awareness import rules
from src.domain.awareness.models import DeskTime
from src.domain.ports import EventLog

# A run at the desk can begin before the day does; this much earlier is read.
_LOOK_BACK = timedelta(days=1)


class AwarenessService:
    """Answers from the recorded presence events. Exceptions from the log pass
    through unchanged."""

    def __init__(self, log: EventLog) -> None:
        self._log = log

    def desk_time(self, at: datetime) -> DeskTime:
        events = self._log.read_since(rules.day_start(at) - _LOOK_BACK)
        return rules.desk_time(events, at)

    def app_minutes(self, start: datetime, end: datetime) -> dict[str, int]:
        events = self._log.read_since(start - _LOOK_BACK)
        return rules.app_minutes(events, start, end)
