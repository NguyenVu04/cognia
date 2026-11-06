"""An index on the time of each event, for reading the events of a day.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('events_by_time', 'events', ['occurred_at'], unique=False)


def downgrade() -> None:
    op.drop_index('events_by_time', table_name='events')
