"""The companion's journal is removed.

Revision ID: 0006
Revises: 0005

The events of the journal go too, because the event log can no longer read
them. A downgrade brings the tables back empty; those events do not come back.
"""
# ruff: noqa: E501

import sqlalchemy as sa
from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM events WHERE kind IN ('reflection_written', 'reflection_deleted')"
    )
    # Children first: with foreign keys on, dropping a parent deletes its rows.
    op.drop_table('message_journal_refs')
    op.drop_table('journal_entry_sources')
    op.drop_table('journal_entries')


def downgrade() -> None:
    op.create_table('journal_entries',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('character_version_id', sa.Text(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('importance', sa.Integer(), nullable=True),
    sa.Column('last_retrieved_at', sa.Text(), nullable=True),
    sa.Column('written_at', sa.Text(), nullable=False),
    sa.Column('embedding', sa.LargeBinary(), nullable=True),
    sa.CheckConstraint('importance BETWEEN 1 AND 10'),
    sa.ForeignKeyConstraint(['character_version_id'], ['character_versions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sqlite_strict=True
    )
    op.create_table('journal_entry_sources',
    sa.Column('journal_entry_id', sa.Text(), nullable=False),
    sa.Column('event_seq', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['event_seq'], ['events.seq'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('journal_entry_id', 'event_seq'),
    sqlite_strict=True
    )
    op.create_index('journal_entry_sources_by_event', 'journal_entry_sources', ['event_seq'], unique=False)
    op.create_table('message_journal_refs',
    sa.Column('message_id', sa.Text(), nullable=False),
    sa.Column('journal_entry_id', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('message_id', 'journal_entry_id'),
    sqlite_strict=True
    )
    op.create_index('message_journal_refs_by_entry', 'message_journal_refs', ['journal_entry_id'], unique=False)
