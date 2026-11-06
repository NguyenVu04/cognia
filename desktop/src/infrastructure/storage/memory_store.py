"""Remembered lines, in the same SQLite file as everything else.

A vector is derived data on the row it describes, as little-endian 32-bit
floats, so it goes when the row goes.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Row, delete, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from src.domain.memory.models import MemoryItem, Vector
from src.domain.ports import MemoryStoreFailed
from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.times import to_text

memory_items = orm.MemoryItem.__table__
memory_refs = orm.MessageMemoryRef.__table__
settings = orm.Settings.__table__

UNREADABLE = (
    "The remembered items cannot be read, so the list cannot be shown. "
    "Nothing was changed."
)
NOT_SAVED = "The change to what I remember could not be saved. Nothing was changed."


class SqliteMemoryStore:
    """A :class:`~src.domain.ports.MemoryStore` kept in the shared
    :class:`Database`. ``close`` does nothing: the owner of the database closes
    it."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── reads ─────────────────────────────────────────────────────────────

    def items(self) -> list[MemoryItem]:
        query = select(memory_items).order_by(memory_items.c.recorded_at.desc())
        return [_item(row) for row in self._read(query)]

    def embedding_model(self) -> str | None:
        rows = self._read(select(settings.c.embedding_model))
        return rows[0].embedding_model if rows else None

    # ── writes ────────────────────────────────────────────────────────────

    def add(self, entry: MemoryItem) -> None:
        self._write(
            insert(memory_items).values(
                id=entry.id,
                kind=entry.kind,
                text=entry.text,
                reason=entry.reason,
                source_message_id=entry.source_message_id,
                importance=entry.importance,
                last_retrieved_at=_time(entry.last_retrieved_at),
                recorded_at=to_text(entry.recorded_at),
                embedding=_pack(entry.embedding),
            )
        )

    def correct(self, entry: MemoryItem, text: str) -> None:
        self._write(
            update(memory_items)
            .where(memory_items.c.id == entry.id)
            .values(text=text, embedding=None)
        )

    def remove(self, entry: MemoryItem) -> None:
        self._write(delete(memory_items).where(memory_items.c.id == entry.id))

    def set_embedding(self, entry: MemoryItem, vector: Vector) -> None:
        self._write(
            update(memory_items)
            .where(memory_items.c.id == entry.id)
            .values(embedding=_pack(vector))
        )

    def link(
        self, message_id: str, entries: Sequence[MemoryItem], now: datetime
    ) -> None:
        if not entries:
            return
        ids = [e.id for e in entries]
        self._write(
            insert(memory_refs).values(
                [{"message_id": message_id, "memory_item_id": i} for i in ids]
            ),
            update(memory_items)
            .where(memory_items.c.id.in_(ids))
            .values(last_retrieved_at=to_text(now)),
        )

    def reset_embeddings(self, model: str) -> None:
        self._write(
            update(memory_items).values(embedding=None),
            update(settings).values(embedding_model=model),
        )

    def close(self) -> None:
        pass

    # ── plumbing ──────────────────────────────────────────────────────────

    def _read(self, query) -> list[Row]:
        try:
            with self._db.transaction() as db:
                return db.execute(query).all()
        except SQLAlchemyError as error:
            raise MemoryStoreFailed(UNREADABLE) from error

    def _write(self, *statements) -> None:
        try:
            with self._db.transaction() as db:
                for statement in statements:
                    db.execute(statement)
        except SQLAlchemyError as error:
            raise MemoryStoreFailed(NOT_SAVED) from error


def _pack(vector: Vector | None) -> bytes | None:
    if vector is None:
        return None
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack(blob: bytes | None) -> Vector | None:
    if blob is None:
        return None
    return struct.unpack(f"<{len(blob) // 4}f", blob)


def _time(moment: datetime | None) -> str | None:
    return to_text(moment) if moment else None


def _moment(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def _item(row: Row) -> MemoryItem:
    try:
        return MemoryItem(
            id=row.id,
            kind=row.kind,
            text=row.text,
            reason=row.reason,
            source_message_id=row.source_message_id,
            importance=row.importance,
            last_retrieved_at=_moment(row.last_retrieved_at),
            recorded_at=datetime.fromisoformat(row.recorded_at),
            embedding=_unpack(row.embedding),
        )
    except (ValueError, struct.error) as error:
        raise MemoryStoreFailed(UNREADABLE) from error
