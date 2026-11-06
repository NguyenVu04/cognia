"""The settings that only the application reads, not the domain."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database

settings = orm.Settings.__table__

NOT_SAVED = "The setting could not be saved. Nothing was changed."


class SettingNotSaved(Exception):
    """A setting the user chose could not be saved, with a sentence saying so."""


class SqliteSettings:
    """The GPU chosen for the chat model, and whether desk awareness is on.

    A failure to read or save the GPU is not reported: a lost choice only means
    that the GPUs are measured again. Desk awareness is the user's choice, so a
    failure to save it is reported, and a failure to read it reads as off.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def chat_device(self) -> str | None:
        try:
            with self._db.transaction() as db:
                return db.execute(select(settings.c.chat_device)).scalar()
        except SQLAlchemyError:
            return None

    def awareness_on(self) -> bool:
        try:
            with self._db.transaction() as db:
                return bool(db.execute(select(settings.c.awareness_on)).scalar())
        except SQLAlchemyError:
            return False

    def set_awareness_on(self, on: bool) -> None:
        """Raises :class:`SettingNotSaved` if the choice cannot be kept."""
        try:
            with self._db.transaction() as db:
                db.execute(update(settings).values(awareness_on=int(on)))
        except SQLAlchemyError as error:
            raise SettingNotSaved(NOT_SAVED) from error

    def set_chat_device(self, name: str) -> None:
        try:
            with self._db.transaction() as db:
                db.execute(update(settings).values(chat_device=name))
        except SQLAlchemyError:
            pass
