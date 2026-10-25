# 3. The whole schema in SQLite, queried through SQLAlchemy Core, migrated by hand

- **Status:** Proposed
- **Date:** 2026-09-26
- **Revised:** 2026-10-24 — a second migration for commitments, the language
  setting and the greeting's basis (COG-UCS-001 v4.0)
- **Revised:** 2026-10-25 — a third migration for the emotion state, the
  temperament, self-adjustments, application totals and the companion's
  journal, and for no default ceiling or quiet hours; the language setting is
  dropped from the second migration, because the companion speaks English only
  (COG-UCS-001 v5.0)
- **Deciders:** Nguyễn Duy Vũ
- **Supersedes:** —
- **Superseded by:** —

## Context

ADR 0002 put conversations in two plain SQLite tables, written by hand with
the standard library's `sqlite3`: one `CREATE TABLE IF NOT EXISTS` string run
on every start, and no migrations. That was enough for two tables. It is not
enough for what the specification still needs stored.

NFR-04 names four kinds of personal data: what the user said about
themselves, session records, observations each carrying its evidence, and
the character with its earlier versions. ADR 0001 adds an append-only
journal and a record of every decision to speak, which UC-17 explains from
and NFR-14 replays. Settings (UC-18), pause (UC-15) and the companion's
position (UC-20) have to survive a restart too.

Version 4.0 of the specification adds two things to store. Commitments the
user mentions (UC-21, FR-29), each with the day they gave, if any, and held only
until they say it is done. And the greeting at the first opening of the day (UC-16), which must be recorded
with the items it mentioned so that it can be explained, and whose existence
today is what decides whether a later opening greets again. Version 4.0 also
let the user choose Vietnamese, which needed a language setting; version 5.0
removed the choice (C-06), so nothing about language is stored.

Version 5.0 gives the companion feelings, initiative and a journal of its own,
and lets it read one more fact from Windows. That adds five things to store. A
temperament on each character version (UC-02, BR-08). The companion's current
emotion state (UC-23), which ADR 0004 computes from journalled events. The
adjustments it makes to itself, each undoable (UC-24, FR-16). Minutes per
application per hour of the day, and the applications the user excluded (C-05,
UC-04-A3). And its journal entries, each with the memories it drew on (UC-25).
It also removes two defaults: there is no daily ceiling and there are no quiet
hours unless the user sets them (BR-01, BR-02).

Two things change when the table count reaches a dozen. First, the schema
will change while users already have a file on disk, and
`CREATE … IF NOT EXISTS` never alters a table that exists. Second, queries
written as strings stop being cheap to get right.

## Decision

**The whole schema is designed now and created in one migration,
`0001_initial.sql`.** It has thirteen tables: conversations and messages;
characters, their immutable versions, traits, trait policies, and the
version–trait join; memory items; a one-row settings table and the message
kinds; sessions; speech decisions; and the journal. Tables for use cases not
yet built exist empty, and their stores arrive with their use cases.

**Version 4.0 arrives as a second migration, `0002_commitments.sql`,
not as an edit to `0001`.** It makes two changes:

- A new `commitments` table: the line exactly as shown back to the user, an
  optional `due_on`, the message it came from, when it was recorded and
  updated, and `due_mentioned_at` — set when the commitment is mentioned once
  after its day has passed (UC-21-A2), so that it is never mentioned for that
  reason again. It is a table of its own rather than a third `kind` in
  `memory_items`, because adding a kind means changing that table's `CHECK`
  constraints, which SQLite can only do by rebuilding the table. UC-12 still
  lists commitments under *you told me*.
- `speech_decisions.basis`, a JSON list of the session and commitment ids a
  greeting mentioned, so UC-17 can say what it was built from. Whether today has
  had its greeting is read from these rows, not kept as a separate flag: one
  fact, one place.

**Version 5.0 arrives as a third migration, `0003_emotion_learning.sql`.** It
makes these changes:

- `settings` is rebuilt by hand, because SQLite cannot drop a `NOT NULL` or
  change a default with `ALTER`. `daily_allowance`, `quiet_start` and
  `quiet_end` become nullable with no default, and `NULL` means none (BR-01,
  BR-02). A new `moods_on`, `0` or `1`, defaults to `1` (UC-18-A2). The rebuild
  copies the existing row as it is; nothing has been released, so no user holds
  the old defaults by choice.
- `character_versions.temperament`, a JSON object of the values UC-02 derives
  and the user may adjust — how far events move the companion, how fast a
  feeling fades, and the resting point in pleasure, arousal and dominance —
  added with `ALTER TABLE … ADD COLUMN`. It belongs to the version, so
  restoring a version restores it (UC-03).
- New rows in `message_kinds` for the kinds the companion may now start
  (UC-22): `remark`, `question`, `commitment`, `checkin` and `adjustment`.
  `break`, `return`, `greeting` and `propose` stay.
- A one-row `emotion_state`: the current point in PAD and the journal `seq` it
  was computed up to. It is a cache. The truth is the journal, from which ADR
  0004 recomputes it, so the row may be rebuilt at any time and is never
  written from anywhere but the domain's output.
- `self_adjustments`: what the companion changed about itself — timing,
  frequency, length or tone — the value before and after, the noticed memory
  item it rests on, and when it was applied and undone. Learned patterns
  themselves are `memory_items` of kind `noticed`, whose `CHECK` already
  refuses one without evidence (FR-34).
- `app_usage`: a local calendar day, an hour from 0 to 23, an application name,
  and minutes, keyed on the first three. There is no column for a window title
  and none finer than an hour, so NFR-03 is enforced by the shape of the table.
  `app_exclusions` holds the names the user excluded; excluding one also deletes
  its rows.
- `companion_journal`: each entry's text, when it was written, and the journal
  `seq`s it drew on. Deleting an entry (UC-25-A2) leaves only those `seq`s
  behind, in `reflection_tombstones`, so it is not written again from the same
  memories. Importance is part of each journalled event's payload, so it needs
  no column.

**A commitment's day is a calendar date, not an instant.** `due_on` is
`YYYY-MM-DD` in the user's local calendar, because the user said "Friday", not a
moment in UTC. It is the one date in the schema that is not a UTC timestamp,
and the exception is deliberate. Where "today" begins (04:00, UC-16) is computed
by the domain from its injected clock and never stored.

**Closing a commitment deletes its row.** It is not marked done and kept: the
specification excludes completion tracking and keeps no history of closed
commitments (section 5). `secure_delete`, below, makes that deletion real.

**Migrations are numbered SQL files, applied once each, tracked by
`PRAGMA user_version`.** `migrate.py` runs each file and its version bump in
one transaction. A later change is a new file (`0002_*.sql`); a shipped file
is never edited. The user's database holds no bookkeeping table.

**SQLAlchemy Core builds the queries. There is no ORM and no Alembic.**
`schema.py` mirrors the migrations as `Table` objects so a query names
`messages.c.created_at` rather than a string. It never creates or alters
anything. The migrations are the truth; the mirror is checked against them
by `python -m src.infrastructure.storage.migrate`, which migrates a scratch
file and compares every table and column. SQLAlchemy is confined to
`src/infrastructure/`, like LangChain in ADR 0002, and `core/models` stays
plain dataclasses.

**One connection, on one thread.** SQLAlchemy's default for a SQLite file is
a `QueuePool` with the same-thread check switched off. That would let the
reply worker quietly open a second connection, undoing ADR 0002's rule that
the wrong thread fails loudly. `open_database` uses `StaticPool` and
`check_same_thread=True`.

**Rules the data must never break are written into the schema.** A "noticed"
memory item cannot exist without evidence (FR-17), and a second open session
cannot be inserted (a partial unique index). NFR-10, no proactive message
without its explanation, stays with the `SpeechGate`: which figures a
message needs depends on its kind, and the gate is where that is known.

**Deletion is real.** `PRAGMA secure_delete=ON` overwrites deleted rows
instead of leaving them in free pages, so an item removed through UC-13 is
gone from the disk (NFR-04). UC-14's erase-all will add a WAL checkpoint and
a `VACUUM`.

**Time is stored in UTC,** as fixed-width ISO-8601 text
(`2026-09-26T08:00:00.123+00:00`), so text order is time order. The rows the
stdlib store wrote in naive local time are converted by `0001`. Naive local
time sorts wrongly for the hour that repeats when clocks go back.

**Ready-made characters are a resource file, not rows.** They ship with the
application and change with releases. They are not the user's data, so
erasing everything must not touch them. Choosing one copies it in as the
user's version 1. The file itself arrives with UC-01's wiring; the four
characters are still an open question in section UC-01 of the
specification.

**A character is structured.** A version has a name, a role, an appearance
and an ordered list of traits, each with its policies. A trait unchanged
between versions keeps its id, so the join table carries it rather than
copying it.

## Consequences

- One more dependency (`sqlalchemy`; the only other package it needs,
  `typing-extensions`, was already installed).
  It is a query builder here, not a persistence framework.
- The schema is described twice, in SQL and in `schema.py`, and nothing but
  the self-check keeps them in step. Forgetting to run it after a migration
  is the failure mode this design accepts in exchange for not having Alembic.
- SQLite cannot drop a constraint or change a column's type with `ALTER`.
  A migration that needs either rebuilds the table by hand (create, copy,
  drop, rename), which is what Alembic's batch mode would otherwise
  generate.
- The file stays readable with nothing but `sqlite3`, as ADR 0002 promised.
  New tables are `STRICT`, so a wrong type is refused rather than stored.
- Empty tables ship before the code that fills them. A design mistake in
  one of them is found later than it would be if each table arrived with
  its use case, and fixing it costs a migration.
- `conversations.character_id` still holds the mockup id `'wren'` and has no
  foreign key. Linking conversations to real characters is part of UC-01.
- The schema has fourteen tables once `0002` runs. UC-14's two erasure levels
  must include `commitments`.
- `0002_commitments.sql` and its mirror in `schema.py` are described
  here but not yet written.
- After `0003` the schema has twenty tables. UC-14's "erase everything
  remembered" must include `emotion_state`, `self_adjustments`, `app_usage`,
  `companion_journal` and `reflection_tombstones`, and keep `app_exclusions`
  and `moods_on`, which are settings.
- The emotion state is a cache over the journal, so removing a past feeling
  (UC-13-A2) means removing the journal rows behind it and recomputing. Removal
  and replay pull against each other here: a replay after a removal is a replay
  of what is left, not of what happened.
- `app_usage.day` is the second local calendar date in the schema, after
  `commitments.due_on`, for the same reason: an hour of the user's day is a
  local hour.
- `0003_emotion_learning.sql` and its mirror in `schema.py` are described here
  but not yet written.

## Alternatives considered

**Keep the standard library only.** A `user_version` runner needs no
dependency, and this was the first recommendation. It was set aside because
the owner wants composed queries across the new tables. It is still the
fallback if SQLAlchemy stops paying for itself.

**SQLAlchemy with Alembic.** Autogenerated migrations and batch mode for
SQLite's missing `ALTER`s. Rejected for now: it adds a second package, an
`alembic_version` table in the user's file, and an `env.py` to run
migrations from inside a desktop application rather than a command line.
Worth revisiting if hand-written table rebuilds become frequent.

**Commitments as a third `kind` in `memory_items`, with a `due_on` column.**
One list for everything the user told the companion. Rejected because both
`CHECK` constraints on that table would change, which in SQLite means a hand
rebuild of the table holding the user's memory, to add a column every other
kind would leave empty.

**Editing `0001_initial.sql` instead of adding `0002`.** Nothing has been
released. Rejected anyway: a database that already ran `0001` would never pick
up the change, and the rule that a shipped migration is never edited is only
worth having if it has no exceptions.

**The ORM.** Mapping classes would either put SQLAlchemy into `core/models`,
which ADR 0001 forbids, or duplicate the dataclasses. Core plus a small
row-to-dataclass function per table is less code.

**`metadata.create_all()` for fresh installs.** It creates missing tables but
never alters existing ones, and a fresh file built from Python would drift
from an upgraded file built from migrations. Only migrations create tables.
