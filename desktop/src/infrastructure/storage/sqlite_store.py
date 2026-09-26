"""Conversations on the user's own disk, in a file anyone can open.

NFR-04 keeps this data on the user's machine with no second copy anywhere, and
the specification is blunt about the shape it should take: "local storage that
cannot be read is worth no more than storage on someone else's server". So the
schema is plain tables with plain columns — no blobs, no pickles, no
framework's private format. ``sqlite3 cognia.sqlite3 "SELECT * FROM messages"``
is a supported way to read your own conversations. The tables themselves are
defined in ``migrations/``; see ADR 0003.

Times are stored in UTC. A naive ``datetime`` handed in is read as local time.

Threading: every method here runs on the GUI thread. ``open_database`` keeps
SQLite's same-thread check on, so touching the store from the reply worker
raises immediately instead of corrupting the file quietly.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Row, delete, insert, literal_column, select, update

from src.core.models import Conversation, Message
from src.infrastructure.storage.database import open_database
from src.infrastructure.storage.schema import conversations, messages

UNTITLED = "New conversation"
TITLE_LENGTH = 40


def title_from(text: str) -> str:
    """The picker's label: the opening line, cut to something that fits."""
    line = " ".join(text.split())
    if len(line) <= TITLE_LENGTH:
        return line or UNTITLED
    return line[: TITLE_LENGTH - 1].rstrip() + "…"


class SqliteConversationStore:
    """A :class:`~src.core.ports.ConversationStore` kept in one SQLite file."""

    def __init__(self, path: Path) -> None:
        self._engine = open_database(path)

    # ── conversations ─────────────────────────────────────────────────────

    def create(self, character_id: str, now: datetime) -> Conversation:
        now = _utc(now)
        conversation = Conversation(
            id=uuid.uuid4().hex,
            character_id=character_id,
            title=UNTITLED,
            started_at=now,
            last_active_at=now,
        )
        with self._engine.begin() as db:
            db.execute(
                insert(conversations).values(
                    id=conversation.id,
                    character_id=conversation.character_id,
                    title=conversation.title,
                    started_at=_text(now),
                    last_active_at=_text(now),
                )
            )
        return conversation

    def conversations(self) -> list[Conversation]:
        with self._engine.connect() as db:
            rows = db.execute(
                select(conversations).order_by(conversations.c.last_active_at.desc())
            ).all()
        return [self._conversation(row) for row in rows]

    def latest(self) -> Conversation | None:
        with self._engine.connect() as db:
            row = db.execute(
                select(conversations)
                .order_by(conversations.c.last_active_at.desc())
                .limit(1)
            ).first()
        return self._conversation(row) if row else None

    def retitle(self, conversation_id: str, title: str) -> None:
        with self._engine.begin() as db:
            db.execute(
                update(conversations)
                .where(conversations.c.id == conversation_id)
                .values(title=title)
            )

    def delete(self, conversation_id: str) -> None:
        with self._engine.begin() as db:
            db.execute(delete(conversations).where(conversations.c.id == conversation_id))

    # ── messages ──────────────────────────────────────────────────────────

    def append(self, message: Message) -> Message:
        """Record a message, and mark its conversation as the active one.

        Both statements land in one transaction: a message that exists but does
        not lift its conversation to the top of the picker would be a message
        the user cannot find.
        """
        message = replace(message, created_at=_utc(message.created_at))
        with self._engine.begin() as db:
            db.execute(
                insert(messages).values(
                    id=message.id,
                    conversation_id=message.conversation_id,
                    role=message.role,
                    text=message.text,
                    note=message.note,
                    created_at=_text(message.created_at),
                )
            )
            db.execute(
                update(conversations)
                .where(conversations.c.id == message.conversation_id)
                .values(last_active_at=_text(message.created_at))
            )
        return message

    def history(self, conversation_id: str, limit: int | None = None) -> list[Message]:
        query = select(messages).where(messages.c.conversation_id == conversation_id)
        rowid = literal_column("rowid")
        with self._engine.connect() as db:
            if limit is None:
                rows = db.execute(query.order_by(messages.c.created_at, rowid)).all()
            else:
                # Take the *last* n, then put them back in reading order.
                rows = db.execute(
                    query.order_by(messages.c.created_at.desc(), rowid.desc()).limit(limit)
                ).all()
                rows.reverse()
        return [self._message(row) for row in rows]

    def close(self) -> None:
        self._engine.dispose()

    # ── rows ──────────────────────────────────────────────────────────────

    @staticmethod
    def _conversation(row: Row) -> Conversation:
        return Conversation(
            id=row.id,
            character_id=row.character_id,
            title=row.title,
            started_at=datetime.fromisoformat(row.started_at),
            last_active_at=datetime.fromisoformat(row.last_active_at),
        )

    @staticmethod
    def _message(row: Row) -> Message:
        return Message(
            id=row.id,
            conversation_id=row.conversation_id,
            role=row.role,
            text=row.text,
            created_at=datetime.fromisoformat(row.created_at),
            note=row.note,
        )


def _utc(moment: datetime) -> datetime:
    """The same instant in UTC; a naive value is taken to be local time."""
    return moment.astimezone(timezone.utc)


def _text(moment: datetime) -> str:
    """The stored form: fixed width, so text order is time order."""
    return _utc(moment).isoformat(timespec="milliseconds")
