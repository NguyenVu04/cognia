"""Erasure by groups of tables, each group in one transaction.

The groups follow the levels of erasure. Inside a group the tables go children
first, so no reference blocks a delete even where no cascade exists.
"""

from __future__ import annotations

import sqlite3

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from src.domain.erasure.models import Group
from src.domain.ports import ErasureFailed
from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database

_TABLES = orm.Base.metadata.tables

# Settings are reset, not deleted; every other table in a group is emptied.
GROUP_TABLES: dict[Group, tuple[str, ...]] = {
    Group.CONVERSATIONS: (
        "message_memory_refs",
        "message_journal_refs",
        "messages",
        "conversations",
    ),
    Group.MEMORY: ("memory_item_evidence", "memory_items"),
    Group.DESK: ("app_usage",),
    Group.LEARNING: ("pattern_evidence", "self_adjustments", "patterns"),
    Group.JOURNAL: ("journal_entry_sources", "journal_entries"),
    Group.SPEECH: ("decision_factors", "speech_decisions"),
    Group.EVENTS: ("emotion_changes", "events"),
    Group.CHARACTER: ("character_proposals", "character_versions"),
    Group.SETTINGS: ("app_exclusions",),
}

# The rows a person would call items.
_COUNTED: dict[Group, tuple[str, ...]] = {
    Group.CONVERSATIONS: ("messages",),
    Group.MEMORY: ("memory_items",),
    Group.DESK: ("app_usage",),
    Group.LEARNING: ("patterns",),
    Group.JOURNAL: ("journal_entries",),
    Group.SPEECH: ("speech_decisions",),
    Group.EVENTS: ("events",),
    Group.CHARACTER: ("character_versions",),
}

RESET_TABLES = ("settings", "message_kinds")

NOT_COUNTED = "What is stored cannot be counted, so nothing was erased."
NOT_ERASED = "Part of what is stored could not be erased. Try again."
NOT_COMPACTED = (
    "The data file could not be rewritten, so removed rows may remain in it. "
    "Try again."
)


class SqliteErasureStore:
    """A :class:`~src.domain.ports.ErasureStore` over the shared
    :class:`Database`."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def count(self, group: Group) -> int:
        if group is Group.SETTINGS:
            return 1
        try:
            with self._db.transaction() as db:
                return sum(
                    db.execute(select(func.count()).select_from(_TABLES[name])).scalar()
                    for name in _COUNTED[group]
                )
        except SQLAlchemyError as error:
            raise ErasureFailed(NOT_COUNTED) from error

    def erase(self, group: Group) -> None:
        try:
            with self._db.transaction() as db:
                for name in GROUP_TABLES[group]:
                    db.execute(delete(_TABLES[name]))
                if group is Group.SETTINGS:
                    for name in RESET_TABLES:
                        db.execute(update(_TABLES[name]).values(_defaults(name)))
        except SQLAlchemyError as error:
            raise ErasureFailed(NOT_ERASED) from error

    def compact(self) -> None:
        try:
            self._db.compact()
        except (sqlite3.Error, SQLAlchemyError) as error:
            raise ErasureFailed(NOT_COMPACTED) from error


def _defaults(name: str) -> dict[str, object]:
    """Each column back to the default that ``orm.py`` states, or NULL."""
    return {
        column.name: (
            column.server_default.arg if column.server_default is not None else None
        )
        for column in _TABLES[name].columns
        if not column.primary_key
    }
