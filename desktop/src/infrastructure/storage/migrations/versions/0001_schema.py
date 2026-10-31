"""The whole schema (ADR 0003).

Revision ID: 0001
Revises:
"""
# ruff: noqa: E501

import sqlalchemy as sa
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('app_exclusions',
    sa.Column('app_name', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('app_name'),
    sqlite_strict=True
    )
    op.create_table('app_usage',
    sa.Column('day', sa.Text(), nullable=False),
    sa.Column('hour', sa.Integer(), nullable=False),
    sa.Column('app_name', sa.Text(), nullable=False),
    sa.Column('minutes', sa.Integer(), nullable=False),
    sa.CheckConstraint('hour BETWEEN 0 AND 23'),
    sa.CheckConstraint('minutes BETWEEN 0 AND 60'),
    sa.PrimaryKeyConstraint('day', 'hour', 'app_name'),
    sqlite_strict=True
    )
    op.create_table('character_versions',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('template_id', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('appearance_id', sa.Text(), nullable=False),
    sa.Column('reactivity', sa.REAL(), nullable=False),
    sa.Column('feeling_half_life_min', sa.REAL(), nullable=False),
    sa.Column('mood_half_life_min', sa.REAL(), nullable=False),
    sa.Column('rest_pleasure', sa.REAL(), nullable=False),
    sa.Column('rest_arousal', sa.REAL(), nullable=False),
    sa.Column('rest_dominance', sa.REAL(), nullable=False),
    sa.Column('origin', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.CheckConstraint("origin IN ('chosen', 'restored', 'proposal')"),
    sa.CheckConstraint('feeling_half_life_min > 0'),
    sa.CheckConstraint('mood_half_life_min > 0'),
    sa.CheckConstraint('reactivity BETWEEN 0 AND 1'),
    sa.CheckConstraint('rest_arousal BETWEEN -1 AND 1'),
    sa.CheckConstraint('rest_dominance BETWEEN -1 AND 1'),
    sa.CheckConstraint('rest_pleasure BETWEEN -1 AND 1'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('number'),
    sqlite_strict=True
    )
    op.create_table('conversations',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('last_active_at', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sqlite_strict=True
    )
    op.create_table('events',
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('occurred_at', sa.Text(), nullable=False),
    sa.Column('utc_offset_min', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('payload', sa.Text(), nullable=False),
    sa.Column('importance', sa.Integer(), nullable=True),
    sa.CheckConstraint('importance BETWEEN 1 AND 10'),
    sa.CheckConstraint('json_valid(payload)'),
    sa.PrimaryKeyConstraint('seq'),
    sqlite_autoincrement=True,
    sqlite_strict=True
    )
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.create_index('events_by_kind', ['kind', 'seq'], unique=False)

    op.create_table('patterns',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('rule_id', sa.Text(), nullable=False),
    sa.Column('parameters', sa.Text(), nullable=False),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('fingerprint', sa.Text(), nullable=False),
    sa.Column('found_at', sa.Text(), nullable=False),
    sa.CheckConstraint('json_valid(parameters)'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fingerprint'),
    sqlite_strict=True
    )
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
    # Autogenerate skips an expression index, so this line is by hand (UC-05-E2).
    op.create_index('one_open_session', 'sessions', [sa.text('(ended_at IS NULL)')], unique=True, sqlite_where=sa.text('ended_at IS NULL'))
    op.create_table('character_proposals',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('base_version_id', sa.Text(), nullable=False),
    sa.Column('pattern_id', sa.Text(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('proposed_description', sa.Text(), nullable=True),
    sa.Column('proposed_reactivity', sa.REAL(), nullable=True),
    sa.Column('proposed_feeling_half_life_min', sa.REAL(), nullable=True),
    sa.Column('proposed_mood_half_life_min', sa.REAL(), nullable=True),
    sa.Column('proposed_rest_pleasure', sa.REAL(), nullable=True),
    sa.Column('proposed_rest_arousal', sa.REAL(), nullable=True),
    sa.Column('proposed_rest_dominance', sa.REAL(), nullable=True),
    sa.Column('fingerprint', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('proposed_at', sa.Text(), nullable=False),
    sa.Column('result_version_id', sa.Text(), nullable=True),
    sa.CheckConstraint("(status = 'approved') = (result_version_id IS NOT NULL)"),
    sa.CheckConstraint("status IN ('open', 'approved', 'refused')"),
    sa.ForeignKeyConstraint(['base_version_id'], ['character_versions.id'], ),
    sa.ForeignKeyConstraint(['pattern_id'], ['patterns.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['result_version_id'], ['character_versions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fingerprint'),
    sqlite_strict=True
    )
    with op.batch_alter_table('character_proposals', schema=None) as batch_op:
        batch_op.create_index('character_proposals_by_base', ['base_version_id'], unique=False)
        batch_op.create_index('character_proposals_by_pattern', ['pattern_id'], unique=False, sqlite_where=sa.text('pattern_id IS NOT NULL'))
        batch_op.create_index('character_proposals_by_result', ['result_version_id'], unique=True, sqlite_where=sa.text('result_version_id IS NOT NULL'))

    op.create_table('emotion_changes',
    sa.Column('event_seq', sa.Integer(), nullable=False),
    sa.Column('character_version_id', sa.Text(), nullable=False),
    sa.Column('pleasure_before', sa.REAL(), nullable=False),
    sa.Column('arousal_before', sa.REAL(), nullable=False),
    sa.Column('dominance_before', sa.REAL(), nullable=False),
    sa.Column('pleasure_after', sa.REAL(), nullable=False),
    sa.Column('arousal_after', sa.REAL(), nullable=False),
    sa.Column('dominance_after', sa.REAL(), nullable=False),
    sa.Column('floor_reached', sa.Integer(), nullable=False),
    sa.CheckConstraint('floor_reached IN (0, 1)'),
    sa.ForeignKeyConstraint(['character_version_id'], ['character_versions.id'], ),
    sa.ForeignKeyConstraint(['event_seq'], ['events.seq'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('event_seq'),
    sqlite_strict=True
    )
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
    op.create_table('message_kinds',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('enabled', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('reduced_since', sa.Text(), nullable=True),
    sa.Column('streak_reset_seq', sa.Integer(), nullable=True),
    sa.CheckConstraint('enabled IN (0, 1)'),
    sa.ForeignKeyConstraint(['streak_reset_seq'], ['events.seq'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sqlite_strict=True
    )
    op.create_table('messages',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('conversation_id', sa.Text(), nullable=False),
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('character_version_id', sa.Text(), nullable=True),
    sa.Column('rating', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.CheckConstraint("role = 'companion' OR character_version_id IS NULL"),
    sa.CheckConstraint("role IN ('user', 'companion')"),
    sa.CheckConstraint('rating IN (-1, 1)'),
    sa.ForeignKeyConstraint(['character_version_id'], ['character_versions.id'], ),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sqlite_strict=True
    )
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.create_index('messages_by_conversation', ['conversation_id', 'created_at'], unique=False)

    op.create_table('pattern_evidence',
    sa.Column('pattern_id', sa.Text(), nullable=False),
    sa.Column('event_seq', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['event_seq'], ['events.seq'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['pattern_id'], ['patterns.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('pattern_id', 'event_seq'),
    sqlite_strict=True
    )
    with op.batch_alter_table('pattern_evidence', schema=None) as batch_op:
        batch_op.create_index('pattern_evidence_by_event', ['event_seq'], unique=False)

    op.create_table('session_intents',
    sa.Column('session_id', sa.Text(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('session_id', 'position'),
    sqlite_strict=True
    )
    op.create_table('settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('character_version_id', sa.Text(), nullable=True),
    sa.Column('daily_ceiling', sa.Integer(), nullable=True),
    sa.Column('quiet_start', sa.Text(), nullable=True),
    sa.Column('quiet_end', sa.Text(), nullable=True),
    sa.Column('break_threshold_min', sa.Integer(), nullable=True),
    sa.Column('moods_on', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('awareness_on', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('paused_at', sa.Text(), nullable=True),
    sa.Column('paused_until', sa.Text(), nullable=True),
    sa.Column('companion_hidden', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('companion_x', sa.Integer(), nullable=True),
    sa.Column('companion_y', sa.Integer(), nullable=True),
    sa.Column('companion_screen', sa.Text(), nullable=True),
    sa.Column('close_hint_shown', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('embedding_model', sa.Text(), nullable=True),
    sa.CheckConstraint('(quiet_start IS NULL) = (quiet_end IS NULL)'),
    sa.CheckConstraint('awareness_on IN (0, 1)'),
    sa.CheckConstraint('break_threshold_min > 0'),
    sa.CheckConstraint('close_hint_shown IN (0, 1)'),
    sa.CheckConstraint('companion_hidden IN (0, 1)'),
    sa.CheckConstraint('daily_ceiling >= 0'),
    sa.CheckConstraint('id = 1'),
    sa.CheckConstraint('moods_on IN (0, 1)'),
    sa.ForeignKeyConstraint(['character_version_id'], ['character_versions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
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

    op.create_table('journal_entry_sources',
    sa.Column('journal_entry_id', sa.Text(), nullable=False),
    sa.Column('event_seq', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['event_seq'], ['events.seq'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('journal_entry_id', 'event_seq'),
    sqlite_strict=True
    )
    with op.batch_alter_table('journal_entry_sources', schema=None) as batch_op:
        batch_op.create_index('journal_entry_sources_by_event', ['event_seq'], unique=False)

    op.create_table('memory_items',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('source_message_id', sa.Text(), nullable=True),
    sa.Column('importance', sa.Integer(), nullable=True),
    sa.Column('last_retrieved_at', sa.Text(), nullable=True),
    sa.Column('recorded_at', sa.Text(), nullable=False),
    sa.Column('embedding', sa.LargeBinary(), nullable=True),
    sa.CheckConstraint("kind = 'told' OR coalesce(reason, '') <> ''"),
    sa.CheckConstraint("kind IN ('told', 'noticed')"),
    sa.CheckConstraint('importance BETWEEN 1 AND 10'),
    sa.ForeignKeyConstraint(['source_message_id'], ['messages.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sqlite_strict=True
    )
    with op.batch_alter_table('memory_items', schema=None) as batch_op:
        batch_op.create_index('memory_items_by_message', ['source_message_id'], unique=False, sqlite_where=sa.text('source_message_id IS NOT NULL'))

    op.create_table('message_journal_refs',
    sa.Column('message_id', sa.Text(), nullable=False),
    sa.Column('journal_entry_id', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('message_id', 'journal_entry_id'),
    sqlite_strict=True
    )
    with op.batch_alter_table('message_journal_refs', schema=None) as batch_op:
        batch_op.create_index('message_journal_refs_by_entry', ['journal_entry_id'], unique=False)

    op.create_table('speech_decisions',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('trigger_seq', sa.Integer(), nullable=True),
    sa.Column('session_id', sa.Text(), nullable=True),
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
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['trigger_seq'], ['events.seq'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sqlite_strict=True
    )
    with op.batch_alter_table('speech_decisions', schema=None) as batch_op:
        batch_op.create_index('speech_decisions_by_kind', ['kind', 'decided_at'], unique=False)
        batch_op.create_index('speech_decisions_by_message', ['message_id'], unique=True, sqlite_where=sa.text('message_id IS NOT NULL'))
        batch_op.create_index('speech_decisions_by_session', ['session_id'], unique=False, sqlite_where=sa.text('session_id IS NOT NULL'))
        batch_op.create_index('speech_decisions_by_trigger', ['trigger_seq'], unique=False, sqlite_where=sa.text('trigger_seq IS NOT NULL'))

    op.create_table('decision_factors',
    sa.Column('decision_id', sa.Text(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('value', sa.REAL(), nullable=True),
    sa.Column('ref_id', sa.Text(), nullable=True),
    sa.Column('event_seq', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['decision_id'], ['speech_decisions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['event_seq'], ['events.seq'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('decision_id', 'position'),
    sqlite_strict=True
    )
    with op.batch_alter_table('decision_factors', schema=None) as batch_op:
        batch_op.create_index('decision_factors_by_event', ['event_seq'], unique=False, sqlite_where=sa.text('event_seq IS NOT NULL'))

    op.create_table('memory_item_evidence',
    sa.Column('memory_item_id', sa.Text(), nullable=False),
    sa.Column('event_seq', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['event_seq'], ['events.seq'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['memory_item_id'], ['memory_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('memory_item_id', 'event_seq'),
    sqlite_strict=True
    )
    with op.batch_alter_table('memory_item_evidence', schema=None) as batch_op:
        batch_op.create_index('memory_item_evidence_by_event', ['event_seq'], unique=False)

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

    op.create_table('message_memory_refs',
    sa.Column('message_id', sa.Text(), nullable=False),
    sa.Column('memory_item_id', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['memory_item_id'], ['memory_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('message_id', 'memory_item_id'),
    sqlite_strict=True
    )
    with op.batch_alter_table('message_memory_refs', schema=None) as batch_op:
        batch_op.create_index('message_memory_refs_by_item', ['memory_item_id'], unique=False)

    op.create_table('self_adjustments',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('pattern_id', sa.Text(), nullable=False),
    sa.Column('aspect', sa.Text(), nullable=False),
    sa.Column('value_before', sa.Text(), nullable=False),
    sa.Column('value_after', sa.Text(), nullable=False),
    sa.Column('applied_at', sa.Text(), nullable=False),
    sa.Column('announced_decision_id', sa.Text(), nullable=True),
    sa.Column('undone_at', sa.Text(), nullable=True),
    sa.CheckConstraint("aspect IN ('timing', 'frequency', 'length', 'tone')"),
    sa.ForeignKeyConstraint(['announced_decision_id'], ['speech_decisions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['pattern_id'], ['patterns.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sqlite_strict=True
    )
    with op.batch_alter_table('self_adjustments', schema=None) as batch_op:
        batch_op.create_index('self_adjustments_by_decision', ['announced_decision_id'], unique=False, sqlite_where=sa.text('announced_decision_id IS NOT NULL'))
        batch_op.create_index('self_adjustments_by_pattern', ['pattern_id'], unique=False)

    op.execute("INSERT INTO settings (id) VALUES (1)")
    # The names on screen are interface copy (ERD section 12.1).
    op.execute(
        "INSERT INTO message_kinds (id) VALUES ('remark'), ('question'), ('break'), "
        "('commitment'), ('checkin'), ('adjustment'), ('proposal'), ('greeting'), "
        "('return')"
    )


def downgrade() -> None:
    with op.batch_alter_table('self_adjustments', schema=None) as batch_op:
        batch_op.drop_index('self_adjustments_by_pattern')
        batch_op.drop_index('self_adjustments_by_decision', sqlite_where=sa.text('announced_decision_id IS NOT NULL'))

    op.drop_table('self_adjustments')
    with op.batch_alter_table('message_memory_refs', schema=None) as batch_op:
        batch_op.drop_index('message_memory_refs_by_item')

    op.drop_table('message_memory_refs')
    with op.batch_alter_table('message_commitment_refs', schema=None) as batch_op:
        batch_op.drop_index('message_commitment_refs_by_commitment')

    op.drop_table('message_commitment_refs')
    with op.batch_alter_table('memory_item_evidence', schema=None) as batch_op:
        batch_op.drop_index('memory_item_evidence_by_event')

    op.drop_table('memory_item_evidence')
    with op.batch_alter_table('decision_factors', schema=None) as batch_op:
        batch_op.drop_index('decision_factors_by_event', sqlite_where=sa.text('event_seq IS NOT NULL'))

    op.drop_table('decision_factors')
    with op.batch_alter_table('speech_decisions', schema=None) as batch_op:
        batch_op.drop_index('speech_decisions_by_trigger', sqlite_where=sa.text('trigger_seq IS NOT NULL'))
        batch_op.drop_index('speech_decisions_by_session', sqlite_where=sa.text('session_id IS NOT NULL'))
        batch_op.drop_index('speech_decisions_by_message', sqlite_where=sa.text('message_id IS NOT NULL'))
        batch_op.drop_index('speech_decisions_by_kind')

    op.drop_table('speech_decisions')
    with op.batch_alter_table('message_journal_refs', schema=None) as batch_op:
        batch_op.drop_index('message_journal_refs_by_entry')

    op.drop_table('message_journal_refs')
    with op.batch_alter_table('memory_items', schema=None) as batch_op:
        batch_op.drop_index('memory_items_by_message', sqlite_where=sa.text('source_message_id IS NOT NULL'))

    op.drop_table('memory_items')
    with op.batch_alter_table('journal_entry_sources', schema=None) as batch_op:
        batch_op.drop_index('journal_entry_sources_by_event')

    op.drop_table('journal_entry_sources')
    with op.batch_alter_table('commitments', schema=None) as batch_op:
        batch_op.drop_index('commitments_by_message', sqlite_where=sa.text('source_message_id IS NOT NULL'))

    op.drop_table('commitments')
    op.drop_table('settings')
    op.drop_table('session_intents')
    with op.batch_alter_table('pattern_evidence', schema=None) as batch_op:
        batch_op.drop_index('pattern_evidence_by_event')

    op.drop_table('pattern_evidence')
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_index('messages_by_conversation')

    op.drop_table('messages')
    op.drop_table('message_kinds')
    op.drop_table('journal_entries')
    op.drop_table('emotion_changes')
    with op.batch_alter_table('character_proposals', schema=None) as batch_op:
        batch_op.drop_index('character_proposals_by_result', sqlite_where=sa.text('result_version_id IS NOT NULL'))
        batch_op.drop_index('character_proposals_by_pattern', sqlite_where=sa.text('pattern_id IS NOT NULL'))
        batch_op.drop_index('character_proposals_by_base')

    op.drop_table('character_proposals')
    op.drop_table('sessions')
    op.drop_table('patterns')
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_index('events_by_kind')

    op.drop_table('events')
    op.drop_table('conversations')
    op.drop_table('character_versions')
    op.drop_table('app_usage')
    op.drop_table('app_exclusions')
