"""Every table of the data file, as ORM classes (ADR 0003, docs/ERD.md).

These classes are the truth about the schema. A change here reaches the file
through a new revision in ``migrations/versions/``, and a test compares the two.

Nothing outside ``infrastructure/storage`` sees a row: a store turns it into a
frozen dataclass, so the domain stays free of SQLAlchemy (ADR 0001).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    REAL,
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

_STRICT = {"sqlite_strict": True}


def _owned(target: str, **options: Any) -> Any:
    """Children that SQLite removes by ``ON DELETE CASCADE``."""
    return relationship(
        target, cascade="all, delete-orphan", passive_deletes=True, **options
    )


def _partial(name: str, column: str, unique: bool = False) -> Index:
    """An index over the rows that have a value in a nullable column."""
    return Index(
        name, column, unique=unique, sqlite_where=text(f"{column} IS NOT NULL")
    )


def _one_of(column: str, *values: str) -> CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({listed})")


def _flag(column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} IN (0, 1)")


def _pad(column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} BETWEEN -1 AND 1")


def _importance() -> CheckConstraint:
    return CheckConstraint("importance BETWEEN 1 AND 10")


class Base(DeclarativeBase):
    # The defaults VARCHAR and FLOAT are not types a STRICT table accepts.
    type_annotation_map = {str: Text, float: REAL, bytes: LargeBinary}


# ── character ─────────────────────────────────────────────────────────────


class CharacterVersionRow(Base):
    """One whole version of the character. A row never changes (UC-03)."""

    __tablename__ = "character_versions"
    __table_args__ = (
        CheckConstraint("reactivity BETWEEN 0 AND 1"),
        CheckConstraint("feeling_half_life_min > 0"),
        CheckConstraint("mood_half_life_min > 0"),
        _pad("rest_pleasure"),
        _pad("rest_arousal"),
        _pad("rest_dominance"),
        _one_of("origin", "chosen", "restored", "proposal"),
        _STRICT,
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(unique=True)
    template_id: Mapped[str]
    name: Mapped[str]
    role: Mapped[str]
    description: Mapped[str]
    appearance_id: Mapped[str]
    reactivity: Mapped[float]
    feeling_half_life_min: Mapped[float]
    mood_half_life_min: Mapped[float]
    rest_pleasure: Mapped[float]
    rest_arousal: Mapped[float]
    rest_dominance: Mapped[float]
    origin: Mapped[str]
    created_at: Mapped[str]


class CharacterProposalRow(Base):
    """A change the companion proposed. A refused row is its tombstone (UC-24-A2)."""

    __tablename__ = "character_proposals"
    __table_args__ = (
        _one_of("status", "open", "approved", "refused"),
        CheckConstraint("(status = 'approved') = (result_version_id IS NOT NULL)"),
        Index("character_proposals_by_base", "base_version_id"),
        _partial("character_proposals_by_pattern", "pattern_id"),
        _partial("character_proposals_by_result", "result_version_id", unique=True),
        _STRICT,
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    base_version_id: Mapped[str] = mapped_column(ForeignKey("character_versions.id"))
    pattern_id: Mapped[str | None] = mapped_column(
        ForeignKey("patterns.id", ondelete="SET NULL")
    )
    summary: Mapped[str]
    proposed_description: Mapped[str | None]
    proposed_reactivity: Mapped[float | None]
    proposed_feeling_half_life_min: Mapped[float | None]
    proposed_mood_half_life_min: Mapped[float | None]
    proposed_rest_pleasure: Mapped[float | None]
    proposed_rest_arousal: Mapped[float | None]
    proposed_rest_dominance: Mapped[float | None]
    fingerprint: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str]
    proposed_at: Mapped[str]
    result_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("character_versions.id")
    )


# ── conversation and provenance ───────────────────────────────────────────


class ConversationRow(Base):
    __tablename__ = "conversations"
    __table_args__ = (_STRICT,)

    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    last_active_at: Mapped[str]

    messages: Mapped[list[MessageRow]] = _owned("MessageRow")


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (
        _one_of("role", "user", "companion"),
        CheckConstraint("role = 'companion' OR character_version_id IS NULL"),
        CheckConstraint("rating IN (-1, 1)"),
        Index("messages_by_conversation", "conversation_id", "created_at"),
        _STRICT,
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str]
    text: Mapped[str]
    character_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("character_versions.id")
    )
    rating: Mapped[int | None]
    created_at: Mapped[str]

    memory_items: Mapped[list[MemoryItemRow]] = relationship(
        secondary="message_memory_refs", passive_deletes=True
    )
    commitments: Mapped[list[CommitmentRow]] = relationship(
        secondary="message_commitment_refs", passive_deletes=True
    )
    journal_entries: Mapped[list[JournalEntryRow]] = relationship(
        secondary="message_journal_refs", passive_deletes=True
    )


class MessageMemoryRefRow(Base):
    __tablename__ = "message_memory_refs"
    __table_args__ = (
        Index("message_memory_refs_by_item", "memory_item_id"),
        _STRICT,
    )

    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    memory_item_id: Mapped[str] = mapped_column(
        ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True
    )


class MessageCommitmentRefRow(Base):
    __tablename__ = "message_commitment_refs"
    __table_args__ = (
        Index("message_commitment_refs_by_commitment", "commitment_id"),
        _STRICT,
    )

    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    commitment_id: Mapped[str] = mapped_column(
        ForeignKey("commitments.id", ondelete="CASCADE"), primary_key=True
    )


class MessageJournalRefRow(Base):
    __tablename__ = "message_journal_refs"
    __table_args__ = (
        Index("message_journal_refs_by_entry", "journal_entry_id"),
        _STRICT,
    )

    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    journal_entry_id: Mapped[str] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="CASCADE"), primary_key=True
    )


# ── memory and commitments ────────────────────────────────────────────────
# ``embedding`` stays the last column and deferred: a row reads its earlier
# columns without walking the vector's overflow pages, and a list never loads it.


class MemoryItemRow(Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        _one_of("kind", "told", "noticed"),
        CheckConstraint("kind = 'told' OR coalesce(reason, '') <> ''"),
        _importance(),
        _partial("memory_items_by_message", "source_message_id"),
        _STRICT,
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str]
    text: Mapped[str]
    reason: Mapped[str | None]
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    importance: Mapped[int | None]
    last_retrieved_at: Mapped[str | None]
    recorded_at: Mapped[str]
    embedding: Mapped[bytes | None] = mapped_column(deferred=True)

    evidence: Mapped[list[MemoryItemEvidenceRow]] = _owned("MemoryItemEvidenceRow")


class MemoryItemEvidenceRow(Base):
    __tablename__ = "memory_item_evidence"
    __table_args__ = (
        Index("memory_item_evidence_by_event", "event_seq"),
        _STRICT,
    )

    memory_item_id: Mapped[str] = mapped_column(
        ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True
    )
    event_seq: Mapped[int] = mapped_column(
        ForeignKey("events.seq", ondelete="CASCADE"), primary_key=True
    )


class CommitmentRow(Base):
    """Something the user has to do. It has no time of day and no status (FR-24)."""

    __tablename__ = "commitments"
    __table_args__ = (
        _importance(),
        _partial("commitments_by_message", "source_message_id"),
        _STRICT,
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    text: Mapped[str]
    due_on: Mapped[str | None]
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    due_passed_mentioned_at: Mapped[str | None]
    importance: Mapped[int | None]
    last_retrieved_at: Mapped[str | None]
    recorded_at: Mapped[str]
    embedding: Mapped[bytes | None] = mapped_column(deferred=True)


# ── work sessions and desk awareness ──────────────────────────────────────


class SessionRow(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        _one_of(
            "closed_how",
            "user",
            "no_answer",
            "last_activity",
            "pause",
            "awareness_off",
        ),
        CheckConstraint("(ended_at IS NULL) = (closed_how IS NULL)"),
        _flag("checkins_requested"),
        # At most one open session (UC-05-E2).
        Index(
            "one_open_session",
            text("(ended_at IS NULL)"),
            unique=True,
            sqlite_where=text("ended_at IS NULL"),
        ),
        _STRICT,
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    started_at: Mapped[str]
    ended_at: Mapped[str | None]
    # Time at the machine, not time worked (BR-06).
    at_machine_seconds: Mapped[int | None]
    closing_answer: Mapped[str | None]
    closed_how: Mapped[str | None]
    checkins_requested: Mapped[int] = mapped_column(server_default=text("0"))
    checkins_stopped_at: Mapped[str | None]

    intents: Mapped[list[SessionIntentRow]] = _owned(
        "SessionIntentRow", order_by="SessionIntentRow.position"
    )


class SessionIntentRow(Base):
    __tablename__ = "session_intents"
    __table_args__ = (_STRICT,)

    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str]


class AppUsageRow(Base):
    """Minutes per application per hour. No column can hold a title (C-05)."""

    __tablename__ = "app_usage"
    __table_args__ = (
        CheckConstraint("hour BETWEEN 0 AND 23"),
        CheckConstraint("minutes BETWEEN 0 AND 60"),
        _STRICT,
    )

    day: Mapped[str] = mapped_column(primary_key=True)
    hour: Mapped[int] = mapped_column(primary_key=True)
    app_name: Mapped[str] = mapped_column(primary_key=True)
    minutes: Mapped[int]


class AppExclusionRow(Base):
    __tablename__ = "app_exclusions"
    __table_args__ = (_STRICT,)

    app_name: Mapped[str] = mapped_column(primary_key=True)


# ── event log and emotion ─────────────────────────────────────────────────


class EventRow(Base):
    """One fact, in order. References and figures, never the user's words (D-03)."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("json_valid(payload)"),
        _importance(),
        Index("events_by_kind", "kind", "seq"),
        {"sqlite_autoincrement": True, **_STRICT},
    )

    seq: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[str]
    utc_offset_min: Mapped[int]
    kind: Mapped[str]
    payload: Mapped[str]
    importance: Mapped[int | None]


class EmotionChangeRow(Base):
    """One change of mood and its cause. A cache of the event log (D-07)."""

    __tablename__ = "emotion_changes"
    __table_args__ = (_flag("floor_reached"), _STRICT)

    event_seq: Mapped[int] = mapped_column(
        ForeignKey("events.seq", ondelete="CASCADE"), primary_key=True
    )
    character_version_id: Mapped[str] = mapped_column(
        ForeignKey("character_versions.id")
    )
    pleasure_before: Mapped[float]
    arousal_before: Mapped[float]
    dominance_before: Mapped[float]
    pleasure_after: Mapped[float]
    arousal_after: Mapped[float]
    dominance_after: Mapped[float]
    floor_reached: Mapped[int]


# ── learning and self-adjustment ──────────────────────────────────────────


class PatternRow(Base):
    __tablename__ = "patterns"
    __table_args__ = (CheckConstraint("json_valid(parameters)"), _STRICT)

    id: Mapped[str] = mapped_column(primary_key=True)
    rule_id: Mapped[str]
    parameters: Mapped[str]
    statement: Mapped[str]
    fingerprint: Mapped[str] = mapped_column(unique=True)
    found_at: Mapped[str]

    evidence: Mapped[list[PatternEvidenceRow]] = _owned("PatternEvidenceRow")
    adjustments: Mapped[list[SelfAdjustmentRow]] = _owned("SelfAdjustmentRow")


class PatternEvidenceRow(Base):
    __tablename__ = "pattern_evidence"
    __table_args__ = (
        Index("pattern_evidence_by_event", "event_seq"),
        _STRICT,
    )

    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE"), primary_key=True
    )
    event_seq: Mapped[int] = mapped_column(
        ForeignKey("events.seq", ondelete="CASCADE"), primary_key=True
    )


class SelfAdjustmentRow(Base):
    __tablename__ = "self_adjustments"
    __table_args__ = (
        _one_of("aspect", "timing", "frequency", "length", "tone"),
        Index("self_adjustments_by_pattern", "pattern_id"),
        _partial("self_adjustments_by_decision", "announced_decision_id"),
        _STRICT,
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("patterns.id", ondelete="CASCADE")
    )
    aspect: Mapped[str]
    value_before: Mapped[str]
    value_after: Mapped[str]
    applied_at: Mapped[str]
    announced_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("speech_decisions.id", ondelete="SET NULL")
    )
    undone_at: Mapped[str | None]


# ── the companion's journal ───────────────────────────────────────────────


class JournalEntryRow(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (_importance(), _STRICT)

    id: Mapped[str] = mapped_column(primary_key=True)
    character_version_id: Mapped[str] = mapped_column(
        ForeignKey("character_versions.id")
    )
    text: Mapped[str]
    importance: Mapped[int | None]
    last_retrieved_at: Mapped[str | None]
    written_at: Mapped[str]
    embedding: Mapped[bytes | None] = mapped_column(deferred=True)

    sources: Mapped[list[JournalEntrySourceRow]] = _owned("JournalEntrySourceRow")


class JournalEntrySourceRow(Base):
    __tablename__ = "journal_entry_sources"
    __table_args__ = (
        Index("journal_entry_sources_by_event", "event_seq"),
        _STRICT,
    )

    journal_entry_id: Mapped[str] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="CASCADE"), primary_key=True
    )
    event_seq: Mapped[int] = mapped_column(
        ForeignKey("events.seq", ondelete="CASCADE"), primary_key=True
    )


# ── speech decisions and explanations ─────────────────────────────────────


class MessageKindRow(Base):
    __tablename__ = "message_kinds"
    __table_args__ = (_flag("enabled"), _STRICT)

    id: Mapped[str] = mapped_column(primary_key=True)
    enabled: Mapped[int] = mapped_column(server_default=text("1"))
    reduced_since: Mapped[str | None]
    streak_reset_seq: Mapped[int | None] = mapped_column(
        ForeignKey("events.seq", ondelete="SET NULL")
    )


class SpeechDecisionRow(Base):
    """One decision to speak, sent or not.

    A sent decision outlives its message, so ``message_id`` can become ``NULL``:
    UC-17 still explains it, and the daily ceiling still counts it. The
    SpeechGate requires a message when it records a send (ERD section 12.2).
    """

    __tablename__ = "speech_decisions"
    __table_args__ = (
        _one_of("outcome", "sent", "withheld", "held", "dropped"),
        _one_of(
            "response",
            "answered",
            "dismissed",
            "passed_over",
            "taken",
            "postponed",
            "silenced",
        ),
        CheckConstraint(
            "outcome NOT IN ('withheld', 'dropped') OR withheld_by IS NOT NULL"
        ),
        # A query over several kinds must name them with IN to use this index.
        Index("speech_decisions_by_kind", "kind", "decided_at"),
        _partial("speech_decisions_by_trigger", "trigger_seq"),
        _partial("speech_decisions_by_session", "session_id"),
        _partial("speech_decisions_by_message", "message_id", unique=True),
        _STRICT,
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(ForeignKey("message_kinds.id"))
    trigger_seq: Mapped[int | None] = mapped_column(
        ForeignKey("events.seq", ondelete="SET NULL")
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL")
    )
    decided_at: Mapped[str]
    outcome: Mapped[str]
    withheld_by: Mapped[str | None]
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    response: Mapped[str | None]

    factors: Mapped[list[DecisionFactorRow]] = _owned(
        "DecisionFactorRow", order_by="DecisionFactorRow.position"
    )


class DecisionFactorRow(Base):
    """One figure behind a decision.

    ``name`` also says the unit of ``value`` and the table of ``ref_id``. The
    domain holds that lookup, so neither is stored (ERD section 12.3).
    """

    __tablename__ = "decision_factors"
    __table_args__ = (
        _partial("decision_factors_by_event", "event_seq"),
        _STRICT,
    )

    decision_id: Mapped[str] = mapped_column(
        ForeignKey("speech_decisions.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    value: Mapped[float | None]
    ref_id: Mapped[str | None]
    event_seq: Mapped[int | None] = mapped_column(
        ForeignKey("events.seq", ondelete="SET NULL")
    )


# ── settings ──────────────────────────────────────────────────────────────


class SettingsRow(Base):
    """Every setting, in one row. ``NULL`` means not set (BR-01, BR-02, FR-09)."""

    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("id = 1"),
        CheckConstraint("daily_ceiling >= 0"),
        CheckConstraint("break_threshold_min > 0"),
        CheckConstraint("(quiet_start IS NULL) = (quiet_end IS NULL)"),
        _flag("moods_on"),
        _flag("awareness_on"),
        _flag("companion_hidden"),
        _flag("close_hint_shown"),
        _STRICT,
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL until the first-run choice is made (UC-01).
    character_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("character_versions.id", ondelete="SET NULL")
    )
    daily_ceiling: Mapped[int | None]
    quiet_start: Mapped[str | None]
    quiet_end: Mapped[str | None]
    break_threshold_min: Mapped[int | None]
    moods_on: Mapped[int] = mapped_column(server_default=text("1"))
    awareness_on: Mapped[int] = mapped_column(server_default=text("0"))
    paused_at: Mapped[str | None]
    paused_until: Mapped[str | None]
    companion_hidden: Mapped[int] = mapped_column(server_default=text("0"))
    companion_x: Mapped[int | None]
    companion_y: Mapped[int | None]
    companion_screen: Mapped[str | None]
    close_hint_shown: Mapped[int] = mapped_column(server_default=text("0"))
    embedding_model: Mapped[str | None]
