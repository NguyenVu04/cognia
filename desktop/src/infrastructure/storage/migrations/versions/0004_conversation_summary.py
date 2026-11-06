"""The summary of the older messages of a long conversation.

Revision ID: 0004
Revises: 0003

Columns are added in place. A batch rebuild of ``conversations`` would delete
every message, because the foreign keys cascade inside the upgrade.
"""

import sqlalchemy as sa
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('conversations', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column(
        'conversations',
        sa.Column(
            'summary_covers', sa.Integer(), server_default=sa.text('0'),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.execute('ALTER TABLE conversations DROP COLUMN summary_covers')
    op.execute('ALTER TABLE conversations DROP COLUMN summary')
