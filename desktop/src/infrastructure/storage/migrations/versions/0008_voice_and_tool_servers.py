"""Two voice settings, and the tool servers the user adds.

Revision ID: 0008
Revises: 0007

Speaking aloud is on by default, and the talk key is Ctrl+Alt+Space. A tool
server row exists only after the user agreed that it may send data off the
machine.
"""
# ruff: noqa: E501

import sqlalchemy as sa
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('tool_servers',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('transport', sa.Text(), nullable=False),
    sa.Column('command', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('args', sa.Text(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('url', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('added_at', sa.Text(), nullable=False),
    sa.Column('consented_at', sa.Text(), nullable=False),
    sa.CheckConstraint("transport <> 'http' OR length(url) > 0"),
    sa.CheckConstraint("transport <> 'stdio' OR length(command) > 0"),
    sa.CheckConstraint("transport IN ('stdio', 'http')"),
    sa.CheckConstraint('json_valid(args)'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    sqlite_strict=True
    )
    # A plain ADD COLUMN keeps the unnamed CHECKs of the table, which a batch
    # rebuild would drop.
    op.execute("ALTER TABLE settings ADD COLUMN speak_aloud INTEGER NOT NULL DEFAULT 1 CHECK (speak_aloud IN (0, 1))")
    op.execute("ALTER TABLE settings ADD COLUMN talk_hotkey TEXT NOT NULL DEFAULT 'Ctrl+Alt+Space'")


def downgrade() -> None:
    checks = (
        "id = 1", "daily_ceiling >= 0", "break_threshold_min > 0",
        "(quiet_start IS NULL) = (quiet_end IS NULL)", "moods_on IN (0, 1)",
        "awareness_on IN (0, 1)", "companion_hidden IN (0, 1)",
        "close_hint_shown IN (0, 1)",
    )
    with op.batch_alter_table(
        'settings', recreate='always',
        table_args=[sa.CheckConstraint(check) for check in checks],
    ) as batch_op:
        batch_op.drop_column('talk_hotkey')
        batch_op.drop_column('speak_aloud')
    op.drop_table('tool_servers')
