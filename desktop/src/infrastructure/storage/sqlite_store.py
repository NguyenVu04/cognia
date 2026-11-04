"""Conversations on the user's own disk, in a file anyone can open.

This data stays on the user's machine with no second copy anywhere, and
the specification is blunt about the shape it should take: "local storage that
cannot be read is worth no more than storage on someone else's server". So the
schema is plain tables with plain columns — no blobs, no pickles, no
framework's private format. ``sqlite3 cognia.sqlite3 "SELECT * FROM messages"``
is a supported way to read your own conversations. The tables themselves are
defined in ``orm.py``.

Times are stored in UTC. A naive ``datetime`` handed in is read as local time.

Threading: every method here runs on the GUI thread. ``open_database`` keeps
SQLite's same-thread check on, so touching the store from the reply worker
raises immediately instead of corrupting the file quietly.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime

from sqlalchemy import Row, delete, insert, literal_column, select, update

from src.domain.conversation.models import COMPANION, USER, Conversation, Message
from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.times import to_text, to_utc

conversations = orm.Conversation.__table__
messages = orm.Message.__table__

UNTITLED = "New conversation"
TITLE_LENGTH = 40

# The file spells a role in full, so that it reads without this code.
_ROLE_TO_STORED = {USER: "user", COMPANION: "companion"}
_ROLE_FROM_STORED = {stored: role for role, stored in _ROLE_TO_STORED.items()}


def title_from(text: str) -> str:
    """The picker's label: the opening line, cut to something that fits."""
    line = " ".join(text.split())
    if len(line) <= TITLE_LENGTH:
        return line or UNTITLED
    return line[: TITLE_LENGTH - 1].rstrip() + "…"


class SqliteConversationStore:
    """A :class:`~src.domain.ports.ConversationStore` kept in the shared
    :class:`Database`. ``close`` does nothing: the owner of the database closes
    it."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── conversations ─────────────────────────────────────────────────────

    def create(self, now: datetime) -> Conversation:
        now = to_utc(now)
        conversation = Conversation(
            id=uuid.uuid4().hex,
            title=UNTITLED,
            last_active_at=now,
        )
        with self._db.transaction() as db:
            db.execute(
                insert(conversations).values(
                    id=conversation.id,
                    title=conversation.title,
                    last_active_at=to_text(now),
                )
            )
        return conversation

    def conversations(self) -> list[Conversation]:
        with self._db.transaction() as db:
            rows = db.execute(
                select(conversations).order_by(conversations.c.last_active_at.desc())
            ).all()
        return [self._conversation(row) for row in rows]

    def latest(self) -> Conversation | None:
        with self._db.transaction() as db:
            row = db.execute(
                select(conversations)
                .order_by(conversations.c.last_active_at.desc())
                .limit(1)
            ).first()
        return self._conversation(row) if row else None

    def retitle(self, conversation_id: str, title: str) -> None:
        with self._db.transaction() as db:
            db.execute(
                update(conversations)
                .where(conversations.c.id == conversation_id)
                .values(title=title)
            )

    def delete(self, conversation_id: str) -> None:
        with self._db.transaction() as db:
            db.execute(
                delete(conversations).where(conversations.c.id == conversation_id)
            )

    # ── messages ──────────────────────────────────────────────────────────

    def append(self, message: Message) -> Message:
        """Record a message, and mark its conversation as the active one.

        Both statements land in one transaction: a message that exists but does
        not lift its conversation to the top of the picker would be a message
        the user cannot find.
        """
        message = replace(message, created_at=to_utc(message.created_at))
        with self._db.transaction() as db:
            db.execute(
                insert(messages).values(
                    id=message.id,
                    conversation_id=message.conversation_id,
                    role=_ROLE_TO_STORED[message.role],
                    text=message.text,
                    created_at=to_text(message.created_at),
                )
            )
            db.execute(
                update(conversations)
                .where(conversations.c.id == message.conversation_id)
                .values(last_active_at=to_text(message.created_at))
            )
        return message

    def history(self, conversation_id: str, limit: int | None = None) -> list[Message]:
        query = select(messages).where(messages.c.conversation_id == conversation_id)
        rowid = literal_column("rowid")
        with self._db.transaction() as db:
            if limit is None:
                rows = db.execute(query.order_by(messages.c.created_at, rowid)).all()
            else:
                # Take the *last* n, then put them back in reading order.
                rows = db.execute(
                    query.order_by(messages.c.created_at.desc(), rowid.desc())
                    .limit(limit)
                ).all()
                rows.reverse()
        return [self._message(row) for row in rows]

    def close(self) -> None:
        pass

    # ── rows ──────────────────────────────────────────────────────────────

    @staticmethod
    def _conversation(row: Row) -> Conversation:
        return Conversation(
            id=row.id,
            title=row.title,
            last_active_at=datetime.fromisoformat(row.last_active_at),
        )

    @staticmethod
    def _message(row: Row) -> Message:
        return Message(
            id=row.id,
            conversation_id=row.conversation_id,
            role=_ROLE_FROM_STORED[row.role],
            text=row.text,
            created_at=datetime.fromisoformat(row.created_at),
        )
