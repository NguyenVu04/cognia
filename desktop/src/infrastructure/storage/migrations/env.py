"""How Alembic reaches the database (ADR 0003).

The application hands in its own connection, so an upgrade runs in the
transaction ``open_database`` holds. The ``alembic`` command has none, and takes
the development file named in ``alembic.ini``.
"""

from alembic import context
from sqlalchemy import create_engine

from src.infrastructure.storage.orm import Base


def _migrate(connection) -> None:
    # SQLite changes most of a table only by rebuilding it.
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    _migrate(connection)
else:
    engine = create_engine(context.config.get_main_option("sqlalchemy.url"))
    with engine.begin() as development:
        _migrate(development)
    engine.dispose()
