"""Minutes per application per hour of the day.

Only the name of the program is kept, never a window title, and only as a total
for each hour.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.dialects.sqlite import insert

from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database

app_usage = orm.AppUsage.__table__


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
