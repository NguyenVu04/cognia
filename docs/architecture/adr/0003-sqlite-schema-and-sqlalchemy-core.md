# 3. The whole schema in SQLite: state tables and a reference-only event log, queried through SQLAlchemy Core

- **Status:** Proposed
- **Date:** 2026-09-26
- **Revised:** 2026-10-25 — rewritten in place for COG-UCS-001 v5.0, approved.
  The schema of [`docs/ERD.md`](../../ERD.md) replaces the earlier design of three
  migrations (`0001` as shipped, `0002` and `0003` described but never written).
  The record stayed Proposed throughout, so it is rewritten rather than superseded,
  at the author's decision
- **Revised:** 2026-10-30 — the connection moves to the core thread (ADR 0005), and
  the schema gains retrieval columns and a UTC offset on events (ADR 0007)
- **Deciders:** Nguyễn Duy Vũ
- **Supersedes:** —
- **Superseded by:** —

## Context

ADR 0002 put conversations in two plain SQLite tables. The first version of this
record then designed the rest of the schema in `0001_initial.sql`, and described two
more migrations for specification versions 4.0 and 5.0. Neither of the two was
written.

A check of that design against the approved specification found requirements with
no place to live:

- which remembered item a reply drew on (UC-09, UC-25), and the rating of a reply
  (UC-09-A2);
- the record of every send to an outside AI service (NFR-02);
- the memory that a pattern was marked wrong, or a proposal refused, so that neither
  comes back (UC-13-A1, UC-24-A2);
- the plain-words description of a character, which UC-03 shows again;
- check-ins asked for in a session (UC-05-A4), and every revised intent (UC-05-A2);
- evidence that a database can check, as G-06 needs at 100%. The earlier design kept
  evidence as free text.

The earlier design also stored the user's words inside the event log, so deleting a
memory item (UC-13) left a copy behind. And the word "journal" named two different
tables. Nothing has been released. The author's local file holds one conversation
and no messages.

## Decision

**We adopt the schema in [`docs/ERD.md`](../../ERD.md).** It has 31 tables. Its section
3 lists fourteen decisions, D-01 to D-14, with their reasons. The decisions that shape
everything else are these:

- **State tables hold what the user owns. The event log holds what happened.**
  Memory items, commitments, sessions and character versions are rows that the user
  reads, corrects and deletes. Feelings, mood history and learned patterns come from
  the event log, and `emotion_state` and `emotion_changes` are caches that the domain
  can compute again (ADR 0001, ADR 0004).
- **The event log holds references and figures, never the user's words.** Its
  payload holds IDs, numbers and closed-set values, including the AI model's class for
  each message. Deleting a row deletes its text, and replay still works (NFR-14).
- **The database checks what it can.** Every table is `STRICT`. Evidence is a join
  table to `events.seq`. The temperament is numeric columns with range `CHECK`s. Settings
  are one typed row where `NULL` means "not set". A partial unique index allows one open
  session.
- **Each kind of thing has its own table.** Commitments, reply sources and
  rejection tombstones each get a table, so each can have real foreign keys and its own
  rule.
- **Keys are UUID text, and time is UTC ISO-8601 text.** `events.seq` is the one
  integer key, because the order of events is part of the data. `commitments.due_on`
  and `app_usage.day` are local calendar days, because the user said "Friday".
  `events.utc_offset_min` keeps the local offset, so a replay finds the same local
  day and hour on any machine.
- **The event log is `events`. The companion's journal is `journal_entries`.** Each
  word has one meaning.

**These decisions from the first version of this record stay as they were:**

- Migrations are numbered SQL files, applied once each and tracked by
  `PRAGMA user_version`. `migrate.py` runs each file and its version bump in one
  transaction. A shipped file is never edited.
- SQLAlchemy Core builds the queries. There is no ORM and no Alembic. `schema.py`
  mirrors the migrations, and `python -m src.infrastructure.storage.migrate` checks the
  mirror against a freshly migrated file. SQLAlchemy stays in `src/infrastructure/`.
- One connection on one thread: `StaticPool` with `check_same_thread=True`. That
  thread is the core thread, not the GUI thread (ADR 0005). `synchronous=FULL` makes
  each commit wait for the disk, and that wait must not stop the drawing.
- `PRAGMA secure_delete=ON`, so a deleted row is gone from the disk (NFR-04). UC-14
  adds a WAL checkpoint and a `VACUUM`.
- Ready-made characters ship as a resource file, not as rows. Choosing one copies it
  in as version 1.

**The change arrives as `0002_redesign.sql`, not as an edit to `0001`.** A file that
already ran `0001` would never run an edited `0001`. The new migration builds every
table of the ERD, copies `conversations` and `messages`, and drops the old tables. The
copy maps `role` from `u` and `c` to `user` and `companion`, and drops the unused
`note` column. The old `settings` and `message_kinds` rows hold only defaults, so the
migration inserts the new defaults instead of copying them.

**A companion message from before the first character keeps no version.** Messages
written under `0001` came from the mockup character, which has no row to point to. So
`messages` checks only one direction: a user message never has a
`character_version_id`. The store sets the version on every new companion message.

## Consequences

**Positive**

- Every requirement in the approved specification has a place in the schema. Section
  15 of the ERD maps each one.
- G-06 becomes a query: every noticed item, pattern, feeling and explanation figure
  links by foreign key to the events behind it.
- UC-13 and UC-14 delete real rows. No copy of the user's words stays in the event
  log or in a tombstone.
- The file stays readable with nothing but `sqlite3`, as ADR 0002 promised.

**Negative**

- 31 tables is a large schema for an application whose domain is not yet built.
  Tables for use cases not yet built ship empty, and a design mistake in one of them
  costs a migration to fix.
- `0002_redesign.sql` rebuilds every table by hand, because SQLite cannot drop a
  constraint with `ALTER`. It must be tested against a file that ran `0001`.
- The rule "a companion message has a character version" lives in the store, not in
  the database, because of the messages written before the first character.
- Removing a past feeling (UC-13-A2) deletes events, so a later replay replays what is
  left, not what happened.
- The `SpeechGate`, not the database, knows which `decision_factors` each kind of
  message needs (NFR-10).
- The schema is described three times: in `docs/ERD.md`, in the SQL migrations and in
  `schema.py`. The migrations are the truth. The self-check keeps `schema.py` in step,
  and nothing checks the ERD.
- `0002_redesign.sql` and its mirror in `schema.py` are described here and not yet
  written.
- The current code still opens the connection on the GUI thread.

**Neutral**

- The ranges of the temperament columns and the 1-to-10 importance scale are proposals
  that trial use sets (ADR 0004).

## Alternatives considered

**Keep the three-migration design and add the missing tables in a fourth.** The
least change to this record. Rejected because the design kept user text in the event
log and evidence as free text. A fourth migration would add tables around both
problems without fixing either.

**Full event sourcing: every table a projection of the event log.** Perfect replay.
Rejected because correcting or deleting one item would mean rewriting events and
rebuilding projections, for the most common thing the user does with their memory.

**Edit `0001_initial.sql` instead of adding `0002`.** Nothing has been released.
Rejected for the reason this record already gave: a file that ran `0001` would never
pick up the change.

**JSON columns for the temperament, the explanation figures and the evidence.** Fewer
tables and columns. Rejected because the database could then check only that the text
is JSON, not that a value is in range or that an event exists.

**Integer keys everywhere.** Smaller and faster joins. Rejected because the current
tables already use UUID text, and a UUID exists before the write, so related rows can
be linked in one transaction.

**SQLAlchemy with Alembic, the ORM, or `metadata.create_all()`.** Rejected for the
reasons the first version of this record gave: a second package and a bookkeeping table
in the user's file, SQLAlchemy in `core/models`, and a fresh file that would drift from
an upgraded one.
