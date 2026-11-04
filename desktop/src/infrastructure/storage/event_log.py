"""The event log, in the same SQLite file as everything else.

A row is never updated. Only the user removes one, and SQLite never gives a
removed seq again. The payload is JSON with sorted keys, so the same payload is
always the same text, and an application name stays readable in the file.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterator
from datetime import datetime

from sqlalchemy import Row, delete, insert, select
from sqlalchemy.exc import SQLAlchemyError

from src.domain.events.models import Event, EventKind, Payload
from src.domain.ports import EventLogFailed
from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.times import to_text

events = orm.Event.__table__

UNREADABLE = (
    "The event log cannot be read, so the companion's feelings cannot be "
    "computed. Nothing was changed."
)
NOT_SAVED = "The event could not be recorded. Nothing was changed."
NOT_REMOVED = "The events could not be removed. Nothing was changed."

# The start reads the whole log. A page at a time keeps memory the same however
# long the log grows.
_PAGE = 500
# SQLite limits the number of values in one statement.
_CHUNK = 500


class SqliteEventLog:
    """A :class:`~src.domain.ports.EventLog` kept in the shared :class:`Database`.

    ``read_from`` reads a page at a time, so it raises while the caller
    iterates, not when it is called. ``close`` does nothing: the owner of the
    database closes it.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def append(
        self,
        occurred_at: datetime,
        utc_offset_min: int,
        kind: EventKind,
        payload: Payload,
        importance: int | None,
    ) -> Event:
        stored_at = to_text(occurred_at)
        stored_payload = json.dumps(dict(payload), sort_keys=True, ensure_ascii=False)
        values = {
            "occurred_at": stored_at,
            "utc_offset_min": utc_offset_min,
            "kind": kind.value,
            "payload": stored_payload,
            "importance": importance,
        }
        try:
            with self._db.transaction() as db:
                result = db.execute(insert(events).values(**values))
        except SQLAlchemyError as error:
            raise EventLogFailed(NOT_SAVED) from error
        # The stored values, so that this event equals the one read back.
        return Event(
            result.inserted_primary_key[0],
            datetime.fromisoformat(stored_at),
            utc_offset_min,
            kind,
            _payload(stored_payload),
            importance,
        )

    def read_from(self, seq: int) -> Iterator[Event]:
        last = seq - 1
        while page := self._page_after(last):
            yield from page
            last = page[-1].seq

    def delete(self, seqs: Collection[int]) -> None:
        seqs = list(seqs)
        try:
            with self._db.transaction() as db:
                for start in range(0, len(seqs), _CHUNK):
                    chunk = seqs[start : start + _CHUNK]
                    db.execute(delete(events).where(events.c.seq.in_(chunk)))
        except SQLAlchemyError as error:
            raise EventLogFailed(NOT_REMOVED) from error

    def close(self) -> None:
        pass

    def _page_after(self, seq: int) -> list[Event]:
        query = (
            select(events).where(events.c.seq > seq).order_by(events.c.seq).limit(_PAGE)
        )
        try:
            with self._db.transaction() as db:
                rows = db.execute(query).all()
            return [_event(row) for row in rows]
        except (SQLAlchemyError, ValueError) as error:
            raise EventLogFailed(UNREADABLE) from error


def _event(row: Row) -> Event:
    return Event(
        seq=row.seq,
        occurred_at=datetime.fromisoformat(row.occurred_at),
        utc_offset_min=row.utc_offset_min,
        kind=EventKind(row.kind),
        payload=_payload(row.payload),
        importance=row.importance,
    )


def _payload(text: str) -> dict:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"a payload must be a JSON object, not {text!r}")
    # JSON has no tuple, so a list of seqs comes back as one.
    return {
        key: tuple(value) if isinstance(value, list) else value
        for key, value in data.items()
    }
