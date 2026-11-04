"""The port through which events are recorded and read back in order.

It says nothing about SQLite: where the log lives is an adapter's business.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from datetime import datetime
from typing import Protocol

from src.domain.events.models import Event, EventKind, Payload


class EventLogFailed(Exception):
    """The event log could not be read or written, with a sentence saying so.
    Carries user-facing text."""


class EventLog(Protocol):
    """Every event, in order. An event is never changed after it is recorded,
    and only the user removes one.

    Each method raises :class:`EventLogFailed` if it cannot do its work.
    """

    def append(
        self,
        occurred_at: datetime,
        utc_offset_min: int,
        kind: EventKind,
        payload: Payload,
        importance: int | None,
    ) -> Event:
        """Record one event after every other and return it with its seq.

        The log gives the seq, so the caller cannot make the event first.
        """
        ...

    def read_from(self, seq: int) -> Iterator[Event]:
        """Every event with ``seq`` or a later one, in order."""
        ...

    def delete(self, seqs: Collection[int]) -> None:
        """Remove these events. A removed seq is never given again."""
        ...

    def close(self) -> None:
        """Release whatever the log is holding."""
        ...
