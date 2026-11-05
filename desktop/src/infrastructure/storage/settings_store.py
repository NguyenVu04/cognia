"""The settings that only the application reads, not the domain."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database

settings = orm.Settings.__table__


class SqliteSettings:
    """The GPU chosen for the chat model.

    A failure to read or save it is not reported: a lost choice only means that
    the GPUs are measured again.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def chat_device(self) -> str | None:
        try:
            with self._db.transaction() as db:
                return db.execute(select(settings.c.chat_device)).scalar()
        except SQLAlchemyError:
            return None

    def set_chat_device(self, name: str) -> None:
        try:
            with self._db.transaction() as db:
                db.execute(update(settings).values(chat_device=name))
        except SQLAlchemyError:
            pass
