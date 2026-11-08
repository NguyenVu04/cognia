"""Minutes per application per hour of the day.

Only the name of the program is kept, never a window title, and only as a total
for each hour.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError

from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database

app_usage = orm.AppUsage.__table__
exclusions = orm.AppExclusion.__table__

NOT_CHANGED = "The list of applications could not be changed. Nothing was changed."


class AppListNotChanged(Exception):
    """An application could not be excluded or counted again."""


class SqliteAppUsage:
    """The hourly totals in the shared :class:`Database`. Runs inside the
    caller's transaction when there is one."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def put(self, day: str, hour: int, minutes: Mapping[str, int]) -> None:
        """Set the minutes of each application in ``hour`` of ``day``. A total
        written again for the same hour replaces the earlier one."""
        rows = [
            {"day": day, "hour": hour, "app_name": app, "minutes": min(60, m)}
            for app, m in minutes.items()
            if app and m > 0
        ]
        if not rows:
            return
        statement = insert(app_usage).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["day", "hour", "app_name"],
            set_={"minutes": statement.excluded.minutes},
        )
        with self._db.transaction() as db:
            db.execute(statement)

    def excluded(self) -> list[str]:
        """The applications that are not counted, by name. Empty if the list
        cannot be read."""
        try:
            with self._db.transaction() as db:
                rows = db.execute(
                    select(exclusions.c.app_name).order_by("app_name")
                ).all()
        except SQLAlchemyError:
            return []
        return [row.app_name for row in rows]

    def exclude(self, name: str) -> None:
        """Stop counting ``name`` and delete its totals. Runs inside the
        caller's transaction when there is one."""
        try:
            with self._db.transaction() as db:
                db.execute(
                    insert(exclusions).values(app_name=name).on_conflict_do_nothing()
                )
                db.execute(delete(app_usage).where(app_usage.c.app_name == name))
        except SQLAlchemyError as error:
            raise AppListNotChanged(NOT_CHANGED) from error

    def include(self, name: str) -> None:
        try:
            with self._db.transaction() as db:
                db.execute(delete(exclusions).where(exclusions.c.app_name == name))
        except SQLAlchemyError as error:
            raise AppListNotChanged(NOT_CHANGED) from error
