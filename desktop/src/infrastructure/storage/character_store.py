"""Character versions, in the same SQLite file as everything else.

A version row is never updated. ``settings.character_version_id`` points at the
version in force, and adding a version moves it in the same transaction, so a
failed change leaves the character in force as it was.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from sqlalchemy import Row, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from src.domain.character.models import Version
from src.domain.emotion.models import Pad, Temperament
from src.domain.ports import CharacterStoreFailed
from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.times import to_text, to_utc

character_versions = orm.CharacterVersion.__table__
settings = orm.Settings.__table__

UNREADABLE = (
    "The saved character history cannot be read, so earlier versions cannot be "
    "shown. The character in force has not changed."
)
NOT_SAVED = "The character could not be saved. The one in force has not changed."


class SqliteCharacterStore:
    """A :class:`~src.domain.ports.CharacterStore` kept in the shared
    :class:`Database`. ``close`` does nothing: the owner of the database closes
    it."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def current(self) -> Version | None:
        query = select(character_versions).join(
            settings, settings.c.character_version_id == character_versions.c.id
        )
        try:
            with self._db.transaction() as db:
                row = db.execute(query).first()
            return _version(row) if row else None
        except (SQLAlchemyError, ValueError) as error:
            raise CharacterStoreFailed(UNREADABLE) from error

    def versions(self) -> list[Version]:
        query = select(character_versions).order_by(character_versions.c.number.desc())
        try:
            with self._db.transaction() as db:
                rows = db.execute(query).all()
            return [_version(row) for row in rows]
        except (SQLAlchemyError, ValueError) as error:
            raise CharacterStoreFailed(UNREADABLE) from error

    def add(self, version: Version) -> Version:
        version = replace(version, created_at=to_utc(version.created_at))
        try:
            with self._db.transaction() as db:
                db.execute(insert(character_versions).values(**_row(version)))
                # The table holds exactly one row.
                db.execute(update(settings).values(character_version_id=version.id))
        except SQLAlchemyError as error:
            raise CharacterStoreFailed(NOT_SAVED) from error
        return version

    def close(self) -> None:
        pass


def _row(version: Version) -> dict[str, object]:
    temperament = version.temperament
    return {
        "id": version.id,
        "number": version.number,
        "template_id": version.template_id,
        "name": version.name,
        "role": version.role,
        "description": version.description,
        "appearance_id": version.appearance_id,
        "reactivity": temperament.reactivity,
        "feeling_half_life_min": temperament.feeling_half_life_min,
        "mood_half_life_min": temperament.mood_half_life_min,
        "rest_pleasure": temperament.rest.pleasure,
        "rest_arousal": temperament.rest.arousal,
        "rest_dominance": temperament.rest.dominance,
        "origin": version.origin,
        "created_at": to_text(version.created_at),
    }


def _version(row: Row) -> Version:
    return Version(
        id=row.id,
        number=row.number,
        template_id=row.template_id,
        name=row.name,
        role=row.role,
        description=row.description,
        appearance_id=row.appearance_id,
        temperament=Temperament(
            reactivity=row.reactivity,
            feeling_half_life_min=row.feeling_half_life_min,
            mood_half_life_min=row.mood_half_life_min,
            rest=Pad(row.rest_pleasure, row.rest_arousal, row.rest_dominance),
        ),
        origin=row.origin,
        created_at=datetime.fromisoformat(row.created_at),
    )
