"""Commitments and work sessions are removed.

Revision ID: 0003
Revises: 0002

The events of the removed kinds go too, because the event log can no longer
read them. A downgrade brings the tables back empty; those events do not come
back.
"""
# ruff: noqa: E501

import sqlalchemy as sa
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

_EVENT_KINDS = (
    "'commitment_added', 'commitment_closed', "
    "'session_opened', 'intent_changed', 'session_closed'"
)
_MESSAGE_KINDS = "'commitment', 'checkin'"
_DECISION_COLUMNS = (
    "id, kind, trigger_seq, decided_at, outcome, withheld_by, message_id, response"
)


def upgrade() -> None:
    op.execute(f"DELETE FROM events WHERE kind IN ({_EVENT_KINDS})")
    op.execute(f"DELETE FROM speech_decisions WHERE kind IN ({_MESSAGE_KINDS})")
    _rebuild_speech_decisions(with_session=False)
    op.execute(f"DELETE FROM message_kinds WHERE id IN ({_MESSAGE_KINDS})")

    with op.batch_alter_table('message_commitment_refs', schema=None) as batch_op:
        batch_op.drop_index('message_commitment_refs_by_commitment')
    op.drop_table('message_commitment_refs')
    with op.batch_alter_table('commitments', schema=None) as batch_op:
        batch_op.drop_index('commitments_by_message', sqlite_where=sa.text('source_message_id IS NOT NULL'))
    op.drop_table('commitments')

    op.drop_table('session_intents')
    op.drop_index('one_open_session', table_name='sessions', sqlite_where=sa.text('ended_at IS NULL'))
    op.drop_table('sessions')


def downgrade() -> None:
    op.create_table('sessions',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('started_at', sa.Text(), nullable=False),
    sa.Column('ended_at', sa.Text(), nullable=True),
    sa.Column('at_machine_seconds', sa.Integer(), nullable=True),
    sa.Column('closing_answer', sa.Text(), nullable=True),
    sa.Column('closed_how', sa.Text(), nullable=True),
    sa.Column('checkins_requested', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('checkins_stopped_at', sa.Text(), nullable=True),
    sa.CheckConstraint("closed_how IN ('user', 'no_answer', 'last_activity', 'pause', 'awareness_off')"),
    sa.CheckConstraint('(ended_at IS NULL) = (closed_how IS NULL)'),
    sa.CheckConstraint('checkins_requested IN (0, 1)'),
    sa.PrimaryKeyConstraint('id'),
    sqlite_strict=True
    )
    op.create_index('one_open_session', 'sessions', [sa.text('(ended_at IS NULL)')], unique=True, sqlite_where=sa.text('ended_at IS NULL'))
    op.create_table('session_intents',
    sa.Column('session_id', sa.Text(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('session_id', 'position'),
    sqlite_strict=True
    )
    op.create_table('commitments',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('due_on', sa.Text(), nullable=True),
    sa.Column('source_message_id', sa.Text(), nullable=True),
    sa.Column('due_passed_mentioned_at', sa.Text(), nullable=True),
    sa.Column('importance', sa.Integer(), nullable=True),
    sa.Column('last_retrieved_at', sa.Text(), nullable=True),
    sa.Column('recorded_at', sa.Text(), nullable=False),
    sa.Column('embedding', sa.LargeBinary(), nullable=True),
    sa.CheckConstraint('importance BETWEEN 1 AND 10'),
    sa.ForeignKeyConstraint(['source_message_id'], ['messages.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sqlite_strict=True
    )
    with op.batch_alter_table('commitments', schema=None) as batch_op:
        batch_op.create_index('commitments_by_message', ['source_message_id'], unique=False, sqlite_where=sa.text('source_message_id IS NOT NULL'))
    op.create_table('message_commitment_refs',
    sa.Column('message_id', sa.Text(), nullable=False),
    sa.Column('commitment_id', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['commitment_id'], ['commitments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('message_id', 'commitment_id'),
    sqlite_strict=True
    )
    with op.batch_alter_table('message_commitment_refs', schema=None) as batch_op:
        batch_op.create_index('message_commitment_refs_by_commitment', ['commitment_id'], unique=False)

    op.execute("INSERT INTO message_kinds (id) VALUES ('commitment'), ('checkin')")
    _rebuild_speech_decisions(with_session=True)


def _rebuild_speech_decisions(with_session: bool) -> None:
    """SQLite cannot drop or add a column that a foreign key names, so the table
    is built again. Dropping the old table cascades to its children while
    foreign keys are on, so their rows are kept aside and put back."""
    op.execute("CREATE TEMP TABLE kept_factors AS SELECT * FROM decision_factors")
    op.execute(
        "CREATE TEMP TABLE kept_announcements AS SELECT id, announced_decision_id "
        "FROM self_adjustments WHERE announced_decision_id IS NOT NULL"
    )

    session = (
        [sa.Column('session_id', sa.Text(), nullable=True)] if with_session else []
    )
    session_key = (
        [sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='SET NULL')]
        if with_session
        else []
    )
    op.create_table('speech_decisions_new',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('trigger_seq', sa.Integer(), nullable=True),
    *session,
    sa.Column('decided_at', sa.Text(), nullable=False),
    sa.Column('outcome', sa.Text(), nullable=False),
    sa.Column('withheld_by', sa.Text(), nullable=True),
    sa.Column('message_id', sa.Text(), nullable=True),
    sa.Column('response', sa.Text(), nullable=True),
    sa.CheckConstraint("outcome IN ('sent', 'withheld', 'held', 'dropped')"),
    sa.CheckConstraint("outcome NOT IN ('withheld', 'dropped') OR withheld_by IS NOT NULL"),
    sa.CheckConstraint("response IN ('answered', 'dismissed', 'passed_over', 'taken', 'postponed', 'silenced')"),
    sa.ForeignKeyConstraint(['kind'], ['message_kinds.id'], ),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='SET NULL'),
    *session_key,
    sa.ForeignKeyConstraint(['trigger_seq'], ['events.seq'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sqlite_strict=True
    )
    op.execute(
        f"INSERT INTO speech_decisions_new ({_DECISION_COLUMNS}) "
        f"SELECT {_DECISION_COLUMNS} FROM speech_decisions"
    )
    op.drop_table('speech_decisions')
    op.rename_table('speech_decisions_new', 'speech_decisions')
    with op.batch_alter_table('speech_decisions', schema=None) as batch_op:
        batch_op.create_index('speech_decisions_by_kind', ['kind', 'decided_at'], unique=False)
        batch_op.create_index('speech_decisions_by_message', ['message_id'], unique=True, sqlite_where=sa.text('message_id IS NOT NULL'))
        if with_session:
            batch_op.create_index('speech_decisions_by_session', ['session_id'], unique=False, sqlite_where=sa.text('session_id IS NOT NULL'))
        batch_op.create_index('speech_decisions_by_trigger', ['trigger_seq'], unique=False, sqlite_where=sa.text('trigger_seq IS NOT NULL'))

    op.execute("INSERT INTO decision_factors SELECT * FROM kept_factors")
    op.execute(
        "UPDATE self_adjustments SET announced_decision_id = ("
        "SELECT announced_decision_id FROM kept_announcements "
        "WHERE kept_announcements.id = self_adjustments.id) "
        "WHERE id IN (SELECT id FROM kept_announcements)"
    )
    op.execute("DROP TABLE kept_factors")
    op.execute("DROP TABLE kept_announcements")
