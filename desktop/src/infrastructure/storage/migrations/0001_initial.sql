-- 0001 — the whole Cognia schema (ADR 0003).
--
-- Applied once, as user_version 1, by migrate.py. Never edit this file after it
-- has shipped: a database that already ran it will not run it again. Change the
-- schema by adding 0002_*.sql, and mirror every change in schema.py.
--
-- Every statement is safe on a fresh file and on a database the stdlib store
-- created before migrations existed (user_version 0, the first two tables
-- already present).
--
-- Plain tables, plain columns: `sqlite3 cognia.sqlite3 "SELECT * FROM messages"`
-- is a supported way to read your own data (ADR 0002). Timestamps are UTC,
-- written as YYYY-MM-DDTHH:MM:SS.mmm+00:00 so text order is time order.


-- ── conversations (ADR 0002, unchanged) ────────────────────────────────────

CREATE TABLE IF NOT EXISTS conversations (
    id             TEXT PRIMARY KEY,
    character_id   TEXT NOT NULL,
    title          TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('u', 'c')),
    text            TEXT NOT NULL,
    note            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS messages_by_conversation
    ON messages (conversation_id, created_at);


-- ── UTC timestamps ─────────────────────────────────────────────────────────
-- The stdlib store wrote naive local times. The 'utc' modifier reads them as
-- local time and converts; rows already in UTC are left alone.

UPDATE conversations SET
    started_at     = strftime('%Y-%m-%dT%H:%M:%f+00:00', started_at, 'utc'),
    last_active_at = strftime('%Y-%m-%dT%H:%M:%f+00:00', last_active_at, 'utc')
WHERE started_at NOT LIKE '%+00:00';

UPDATE messages SET
    created_at = strftime('%Y-%m-%dT%H:%M:%f+00:00', created_at, 'utc')
WHERE created_at NOT LIKE '%+00:00';


-- ── characters (UC-01, UC-02, UC-03, FR-01–FR-04) ──────────────────────────
-- A version is never updated: editing or restoring inserts a new one, so every
-- earlier version stays restorable. Appearance is versioned with the voice.
-- Ready-made characters are not stored here; they ship as a resource file and
-- choosing one copies it in as version 1.

CREATE TABLE IF NOT EXISTS characters (
    id                 TEXT PRIMARY KEY,
    template_id        TEXT,
    current_version_id TEXT REFERENCES character_versions(id),
    created_at         TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS character_versions (
    id                       TEXT PRIMARY KEY,
    character_id             TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    number                   INTEGER NOT NULL,
    name                     TEXT NOT NULL,
    role                     TEXT NOT NULL,
    appearance               TEXT NOT NULL,
    change_summary           TEXT NOT NULL,
    parent_version_id        TEXT REFERENCES character_versions(id),
    restored_from_version_id TEXT REFERENCES character_versions(id),
    created_at               TEXT NOT NULL,
    UNIQUE (character_id, number)
) STRICT;

-- A trait belongs to no single version: an unchanged trait carries over to the
-- next version under the same id.
CREATE TABLE IF NOT EXISTS character_traits (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS character_trait_policies (
    trait_id TEXT NOT NULL REFERENCES character_traits(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    text     TEXT NOT NULL,
    PRIMARY KEY (trait_id, position)
) STRICT;

CREATE TABLE IF NOT EXISTS character_version_traits (
    version_id TEXT NOT NULL REFERENCES character_versions(id) ON DELETE CASCADE,
    trait_id   TEXT NOT NULL REFERENCES character_traits(id),
    position   INTEGER NOT NULL,
    PRIMARY KEY (version_id, trait_id)
) STRICT;


-- ── memory (UC-09, UC-10, UC-12, UC-13, FR-14, FR-17, FR-18) ───────────────
-- "told" is what the user said, in the exact line shown back to them.
-- "noticed" is what the companion concluded, and never exists without the
-- evidence for it (FR-17).

CREATE TABLE IF NOT EXISTS memory_items (
    id                TEXT PRIMARY KEY,
    kind              TEXT NOT NULL CHECK (kind IN ('told', 'noticed')),
    text              TEXT NOT NULL,
    evidence          TEXT,
    source_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
    recorded_at       TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    CHECK (kind = 'told' OR coalesce(evidence, '') <> '')
) STRICT;


-- ── settings (UC-01, UC-04, UC-15, UC-18, UC-20) ───────────────────────────
-- Exactly one row. character_id IS NULL means the first-run choice has not
-- been made yet (UC-01 precondition).

CREATE TABLE IF NOT EXISTS settings (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    character_id        TEXT REFERENCES characters(id) ON DELETE SET NULL,
    daily_allowance     INTEGER NOT NULL DEFAULT 3 CHECK (daily_allowance >= 0),  -- BR-01
    quiet_start         TEXT NOT NULL DEFAULT '22:00',                             -- BR-02
    quiet_end           TEXT NOT NULL DEFAULT '07:00',
    break_threshold_min INTEGER NOT NULL DEFAULT 90 CHECK (break_threshold_min > 0),
    awareness_on        INTEGER NOT NULL DEFAULT 0 CHECK (awareness_on IN (0, 1)),
    paused              INTEGER NOT NULL DEFAULT 0 CHECK (paused IN (0, 1)),
    paused_until        TEXT,               -- NULL while paused: until switched back on
    companion_x         INTEGER,
    companion_y         INTEGER,
    companion_screen    TEXT
) STRICT;

INSERT OR IGNORE INTO settings (id) VALUES (1);

-- The kinds of proactive message (UC-06, UC-08, UC-16, UC-11), each switchable
-- (FR-22) and reducible when ignored (FR-23). Their names are UI copy.
CREATE TABLE IF NOT EXISTS message_kinds (
    id            TEXT PRIMARY KEY,
    enabled       INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    reduced_since TEXT
) STRICT;

INSERT OR IGNORE INTO message_kinds (id) VALUES
    ('break'), ('return'), ('greeting'), ('propose');


-- ── sessions (UC-05, UC-07, UC-08, FR-07, FR-10) ───────────────────────────
-- intent_original keeps the first line when the intent is revised (UC-05).
-- at_machine_seconds is time at the machine, not time worked (BR-06).

CREATE TABLE IF NOT EXISTS sessions (
    id                 TEXT PRIMARY KEY,
    intent             TEXT,
    intent_original    TEXT,
    started_at         TEXT NOT NULL,
    ended_at           TEXT,
    at_machine_seconds INTEGER,
    closing_answer     TEXT,
    closed_how         TEXT CHECK (closed_how IN ('user', 'no_answer', 'last_activity'))
) STRICT;

-- At most one open session.
CREATE UNIQUE INDEX IF NOT EXISTS one_open_session
    ON sessions (ended_at IS NULL) WHERE ended_at IS NULL;


-- ── speech decisions (UC-06, UC-17, UC-19, NFR-10, NFR-14) ─────────────────
-- Every decision to speak, sent or withheld, with the figures it was made
-- from. UC-17 reads these; withheld_by names the rule (e.g. 'BR-02') so the
-- explanation stays truthful. Wording is presentation: only figures are kept.
-- NFR-10 (no explanation, no message) is enforced by the SpeechGate.

CREATE TABLE IF NOT EXISTS speech_decisions (
    id                TEXT PRIMARY KEY,
    kind              TEXT NOT NULL REFERENCES message_kinds(id),
    session_id        TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    decided_at        TEXT NOT NULL,
    outcome           TEXT NOT NULL CHECK (outcome IN ('sent', 'withheld')),
    withheld_by       TEXT,
    text              TEXT,
    observed_seconds  INTEGER,
    threshold_seconds INTEGER,
    delayed_seconds   INTEGER,
    delayed_by        TEXT,
    allowance_used    INTEGER,
    allowance_total   INTEGER,
    response          TEXT CHECK (response IN ('taken', 'postponed', 'ignored', 'dismissed')),
    responded_at      TEXT
) STRICT;


-- ── journal (ADR 0001, NFR-14) ─────────────────────────────────────────────
-- Append-only, in arrival order: what entered the queue, so a decision can be
-- replayed. It records observations about the user, so it is personal data and
-- is covered by UC-12 to UC-14 like everything else.

CREATE TABLE IF NOT EXISTS journal (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(payload))
) STRICT;
