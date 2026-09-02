"""Conversations on the user's own disk, in a file anyone can open.

NFR-04 keeps this data on the user's machine with no second copy anywhere, and
the specification is blunt about the shape it should take: "local storage that
cannot be read is worth no more than storage on someone else's server". So the
schema is two plain tables with plain columns — no blobs, no pickles, no
framework's private format. ``sqlite3 cognia.sqlite3 "SELECT * FROM messages"``
is a supported way to read your own conversations.

Threading: every method here runs on the GUI thread. The connection is opened
with SQLite's default same-thread check left on, so touching the store from the
reply worker raises immediately instead of corrupting the file quietly.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from src.core.models import Conversation, Message

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id             TEXT PRIMARY KEY,
    character_id   TEXT NOT NULL,
    title          TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('u', 'c')),
    text            TEXT NOT NULL,
    note            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS messages_by_conversation
    ON messages (conversation_id, created_at);
"""

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
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        # WAL survives an abrupt shutdown; FULL means a committed message is on
        # the platter before we say it was recorded. NFR-08 asks for both.
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ── conversations ─────────────────────────────────────────────────────

    def create(self, character_id: str, now: datetime) -> Conversation:
        conversation = Conversation(
            id=uuid.uuid4().hex,
            character_id=character_id,
            title=UNTITLED,
            started_at=now,
            last_active_at=now,
        )
        self._db.execute(
            "INSERT INTO conversations VALUES (?, ?, ?, ?, ?)",
            (
                conversation.id,
                conversation.character_id,
                conversation.title,
                conversation.started_at.isoformat(),
                conversation.last_active_at.isoformat(),
            ),
        )
        self._db.commit()
        return conversation

    def conversations(self) -> list[Conversation]:
        rows = self._db.execute(
            "SELECT * FROM conversations ORDER BY last_active_at DESC"
        ).fetchall()
        return [self._conversation(row) for row in rows]

    def latest(self) -> Conversation | None:
        row = self._db.execute(
            "SELECT * FROM conversations ORDER BY last_active_at DESC LIMIT 1"
        ).fetchone()
        return self._conversation(row) if row else None

    def retitle(self, conversation_id: str, title: str) -> None:
        self._db.execute(
            "UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id)
        )
        self._db.commit()

    def delete(self, conversation_id: str) -> None:
        self._db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        self._db.commit()

    # ── messages ──────────────────────────────────────────────────────────

    def append(self, message: Message) -> Message:
        """Record a message, and mark its conversation as the active one.

        Both statements land in one transaction: a message that exists but does
        not lift its conversation to the top of the picker would be a message
        the user cannot find.
        """
        with self._db:
            self._db.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
                (
                    message.id,
                    message.conversation_id,
                    message.role,
                    message.text,
                    message.note,
                    message.created_at.isoformat(),
                ),
            )
            self._db.execute(
                "UPDATE conversations SET last_active_at = ? WHERE id = ?",
                (message.created_at.isoformat(), message.conversation_id),
            )
        return message

    def history(self, conversation_id: str, limit: int | None = None) -> list[Message]:
        if limit is None:
            rows = self._db.execute(
                "SELECT * FROM messages WHERE conversation_id = ?"
                " ORDER BY created_at, rowid",
                (conversation_id,),
            ).fetchall()
        else:
            # Take the *last* n, then put them back in reading order.
            rows = self._db.execute(
                "SELECT * FROM messages WHERE conversation_id = ?"
                " ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
            rows = list(reversed(rows))
        return [self._message(row) for row in rows]

    def close(self) -> None:
        self._db.close()

    # ── rows ──────────────────────────────────────────────────────────────

    @staticmethod
    def _conversation(row: sqlite3.Row) -> Conversation:
        return Conversation(
            id=row["id"],
            character_id=row["character_id"],
            title=row["title"],
            started_at=datetime.fromisoformat(row["started_at"]),
            last_active_at=datetime.fromisoformat(row["last_active_at"]),
        )

    @staticmethod
    def _message(row: sqlite3.Row) -> Message:
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            text=row["text"],
            created_at=datetime.fromisoformat(row["created_at"]),
            note=row["note"],
        )
