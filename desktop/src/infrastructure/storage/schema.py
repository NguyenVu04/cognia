"""The tables, as SQLAlchemy Core sees them — for building queries only.

``migrations/*.sql`` is the source of truth for what is in the file; this is a
mirror of it, so a query can say ``messages.c.created_at`` instead of a string.
Nothing here creates or alters a table (``create_all`` is never called), and
checks and indexes live only in the SQL. There is no Alembic to notice when the
two disagree, so ``python -m src.infrastructure.storage.migrate`` compares
every table and column here against a freshly migrated file.
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, Text

metadata = MetaData()

# ── conversations ─────────────────────────────────────────────────────────

conversations = Table(
    "conversations", metadata,
    Column("id", Text, primary_key=True),
    Column("character_id", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("started_at", Text, nullable=False),
    Column("last_active_at", Text, nullable=False),
)

messages = Table(
    "messages", metadata,
    Column("id", Text, primary_key=True),
    Column("conversation_id", Text, ForeignKey("conversations.id"), nullable=False),
    Column("role", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)

# ── characters ────────────────────────────────────────────────────────────

characters = Table(
    "characters", metadata,
    Column("id", Text, primary_key=True),
    Column("template_id", Text),
    Column("current_version_id", Text,
           ForeignKey("character_versions.id", use_alter=True)),
    Column("created_at", Text, nullable=False),
)

character_versions = Table(
    "character_versions", metadata,
    Column("id", Text, primary_key=True),
    Column("character_id", Text, ForeignKey("characters.id"), nullable=False),
    Column("number", Integer, nullable=False),
    Column("name", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("appearance", Text, nullable=False),
    Column("change_summary", Text, nullable=False),
    Column("parent_version_id", Text, ForeignKey("character_versions.id")),
    Column("restored_from_version_id", Text, ForeignKey("character_versions.id")),
    Column("created_at", Text, nullable=False),
)

character_traits = Table(
    "character_traits", metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False),
)

character_trait_policies = Table(
    "character_trait_policies", metadata,
    Column("trait_id", Text, ForeignKey("character_traits.id"), primary_key=True),
    Column("position", Integer, primary_key=True),
    Column("text", Text, nullable=False),
)

character_version_traits = Table(
    "character_version_traits", metadata,
    Column("version_id", Text, ForeignKey("character_versions.id"), primary_key=True),
    Column("trait_id", Text, ForeignKey("character_traits.id"), primary_key=True),
    Column("position", Integer, nullable=False),
)

# ── memory ────────────────────────────────────────────────────────────────

memory_items = Table(
    "memory_items", metadata,
    Column("id", Text, primary_key=True),
    Column("kind", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("evidence", Text),
    Column("source_message_id", Text, ForeignKey("messages.id")),
    Column("recorded_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

# ── settings ──────────────────────────────────────────────────────────────

settings = Table(
    "settings", metadata,
    Column("id", Integer, primary_key=True),
    Column("character_id", Text, ForeignKey("characters.id")),
    Column("daily_allowance", Integer, nullable=False),
    Column("quiet_start", Text, nullable=False),
    Column("quiet_end", Text, nullable=False),
    Column("break_threshold_min", Integer, nullable=False),
    Column("awareness_on", Integer, nullable=False),
    Column("paused", Integer, nullable=False),
    Column("paused_until", Text),
    Column("companion_x", Integer),
    Column("companion_y", Integer),
    Column("companion_screen", Text),
)

message_kinds = Table(
    "message_kinds", metadata,
    Column("id", Text, primary_key=True),
    Column("enabled", Integer, nullable=False),
    Column("reduced_since", Text),
)

# ── sessions, speech decisions, journal ───────────────────────────────────

sessions = Table(
    "sessions", metadata,
    Column("id", Text, primary_key=True),
    Column("intent", Text),
    Column("intent_original", Text),
    Column("started_at", Text, nullable=False),
    Column("ended_at", Text),
    Column("at_machine_seconds", Integer),
    Column("closing_answer", Text),
    Column("closed_how", Text),
)

speech_decisions = Table(
    "speech_decisions", metadata,
    Column("id", Text, primary_key=True),
    Column("kind", Text, ForeignKey("message_kinds.id"), nullable=False),
    Column("session_id", Text, ForeignKey("sessions.id")),
    Column("decided_at", Text, nullable=False),
    Column("outcome", Text, nullable=False),
    Column("withheld_by", Text),
    Column("text", Text),
    Column("observed_seconds", Integer),
    Column("threshold_seconds", Integer),
    Column("delayed_seconds", Integer),
    Column("delayed_by", Text),
    Column("allowance_used", Integer),
    Column("allowance_total", Integer),
    Column("response", Text),
    Column("responded_at", Text),
)

journal = Table(
    "journal", metadata,
    Column("seq", Integer, primary_key=True),
    Column("occurred_at", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("payload", Text, nullable=False),
)
