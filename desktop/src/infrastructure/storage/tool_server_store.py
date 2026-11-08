"""The tool servers the user added, in the shared database."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.domain.ports.tool_server_store import ToolServerStoreFailed
from src.domain.tools.models.tool_server import ToolServer
from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.times import to_text

servers = orm.ToolServer.__table__

NOT_READ = "The add-ons could not be read."
NOT_SAVED = "The add-on could not be saved. Nothing was changed."
NAME_TAKEN = "An add-on with that name already exists. Choose another name."


class SqliteToolServerStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, server: ToolServer) -> None:
        try:
            with self._db.transaction() as db:
                db.execute(insert(servers).values(
                    id=server.id,
                    name=server.name,
                    transport=server.transport,
                    command=server.command,
                    args=json.dumps(list(server.args)),
                    url=server.url,
                    added_at=to_text(server.added_at),
                    consented_at=to_text(server.consented_at),
                ))
        except IntegrityError as error:
            raise ToolServerStoreFailed(NAME_TAKEN) from error
        except SQLAlchemyError as error:
            raise ToolServerStoreFailed(NOT_SAVED) from error

    def all(self) -> list[ToolServer]:
        try:
            with self._db.transaction() as db:
                rows = db.execute(select(servers).order_by(servers.c.name)).all()
        except SQLAlchemyError as error:
            raise ToolServerStoreFailed(NOT_READ) from error
        return [
            ToolServer(
                id=row.id,
                name=row.name,
                transport=row.transport,
                command=row.command,
                args=tuple(json.loads(row.args)),
                url=row.url,
                added_at=datetime.fromisoformat(row.added_at),
                consented_at=datetime.fromisoformat(row.consented_at),
            )
            for row in rows
        ]

    def remove(self, server_id: str) -> None:
        try:
            with self._db.transaction() as db:
                db.execute(delete(servers).where(servers.c.id == server_id))
        except SQLAlchemyError as error:
            raise ToolServerStoreFailed(NOT_SAVED) from error
