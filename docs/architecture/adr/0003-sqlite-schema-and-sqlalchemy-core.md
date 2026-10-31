# 3. The whole schema in SQLite: state tables and a reference-only event log, stated as ORM classes and applied by Alembic

- **Status:** Proposed
- **Date:** 2026-09-26
- **Revised:** 2026-10-25 — rewritten in place for COG-UCS-001 v5.0, approved.
  The schema of [`docs/ERD.md`](../../ERD.md) replaces the earlier design of three
  migrations (`0001` as shipped, `0002` and `0003` described but never written).
  The record stayed Proposed throughout, so it is rewritten rather than superseded,
  at the author's decision
- **Revised:** 2026-10-30 — the connection moves to the core thread (ADR 0005), and
  the schema gains retrieval columns and a UTC offset on events (ADR 0007)
- **Revised:** 2026-10-31 — rewritten in place for COG-UCS-001 v5.4, at the author's
  decision. SQLAlchemy ORM classes replace SQLAlchemy Core and the mirror in `schema.py`.
  Alembic replaces the numbered SQL files. The schema falls from 31 tables to 25
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
- the memory that a pattern was marked wrong, or a proposal refused, so that neither
  comes back (UC-13-A1, UC-24-A2);
- the plain-words description of a character, which UC-03 shows again;
- check-ins asked for in a session (UC-05-A4), and every revised intent (UC-05-A2);
- evidence that a database can check, as G-06 needs at 100%. The earlier design kept
  evidence as free text.

The earlier design also stored the user's words inside the event log, so deleting a
memory item (UC-13) left a copy behind. And the word "journal" named two different
tables. Nothing has been released. The author's local file held one conversation
and no messages.

A later check of the 31-table design found these problems:

- `decision_factors` broke third normal form, because `name` set both `unit` and the
  table of `ref_id`;
- four tombstone tables held a second copy of facts that the event log must hold, because
  a rule reads only the log;
- `emotion_state` had no reader, because the core thread folds the log at each start;
- many columns had no reader, or copied the time of an event;
- most foreign keys had no index, so each deleted event scanned the evidence tables;
- two definitions of the schema, in SQL and in `schema.py`, needed a self-check.

## Decision

**We adopt the schema in [`docs/ERD.md`](../../ERD.md).** It has 25 tables. Its section
3 lists its decisions with their reasons, and sections 3.2 and 3.3 give the check of
normal forms and of indexes. The decisions that shape everything else are these:

- **State tables hold what the user owns. The event log holds what happened.**
  Memory items, commitments, sessions and character versions are rows that the user
  reads, corrects and deletes. Feelings, mood history and learned patterns come from
  the event log, and `emotion_changes` is a cache that the domain can compute again
  (ADR 0001, ADR 0004). The current emotion point stays in memory (D-38 of
  `ARCHITECTURE.md`).
- **The event log holds references and figures, never the user's words.** Its
  payload holds IDs, numbers and closed-set values, including the AI model's class for
  each message. Deleting a row deletes its text, and replay still works (NFR-13).
- **A tombstone is an event.** `pattern_rejected` and `reflection_deleted` hold the
  fingerprint and the seqs (D-37 of `ARCHITECTURE.md`). A refused proposal and an undone
  adjustment stay as rows in their own tables.
- **The database checks what it can.** Every table is `STRICT`. Evidence is a join
  table to `events.seq`. The temperament is numeric columns with range `CHECK`s. Settings
  are one typed row where `NULL` means "not set". A partial unique index allows one open
  session.
- **Keys are UUID text, and time is UTC ISO-8601 text.** `events.seq` is the one
  integer key, because the order of events is part of the data. `commitments.due_on`
  and `app_usage.day` are local calendar days, because the user said "Friday".
  `events.utc_offset_min` keeps the local offset, so a replay finds the same local
  day and hour on any machine.
- **The event log is `events`. The companion's journal is `journal_entries`.** Each
  word has one meaning.

**SQLAlchemy ORM classes state the schema.** `orm.py` in `infrastructure/storage` holds
one class for each table. These classes are the truth about the schema. SQLAlchemy stays
in `src/infrastructure/`. A store turns a row into a frozen dataclass, so `domain/`
imports no SQLAlchemy (ADR 0001).

**Alembic applies the schema.** `open_database` upgrades the file to the newest revision
at each start, in one transaction. A shipped revision is never edited. A test compares
the ORM classes with a migrated file. Autogenerate does not see an expression index or a
changed `CHECK`, so a person reads each revision.

**One revision builds the whole schema.** Nothing has been released. `0001_schema.py`
creates all 25 tables. A file from before this revision is refused, and it stays as it
was. The user moves that file away.

**These decisions from the first version of this record stay as they were:**

- One connection on one thread: `StaticPool` with `check_same_thread=True`. That
  thread is the core thread, not the GUI thread (ADR 0005). `synchronous=FULL` makes
  each commit wait for the disk, and that wait must not stop the drawing.
- `PRAGMA secure_delete=ON`, so a deleted row is gone from the disk (NFR-03). UC-14
  adds a WAL checkpoint and a `VACUUM`.
- Ready-made characters ship as a resource file, not as rows. Choosing one copies it
  in as version 1.

**The database does not hold two rules, because a row can legally break them.** A sent
decision outlives its message, so the `SpeechGate` requires `message_id` when it records
a send. The store must set `character_version_id` on each new companion message, and
that rule cannot be a `CHECK` until a character row exists.

## Consequences

**Positive**

- Every requirement in the approved specification has a place in the schema. Section
  15 of the ERD maps each one.
- G-06 becomes a query: every noticed item, pattern, feeling and explanation figure
  links by foreign key to the events behind it.
- UC-13 and UC-14 delete real rows. No copy of the user's words stays in the event
  log or in a tombstone.
- The file stays readable with nothing but `sqlite3`, as ADR 0002 promised.
- One definition of the schema. Twenty-two tables are in BCNF. The other three have a
  derived `embedding` column, by decision.
- A delete of events no longer scans the evidence tables.

**Negative**

- 25 tables is a large schema for an application whose domain is not yet built.
  Tables for use cases not yet built ship empty, and a design mistake in one of them
  costs a revision to fix.
- Alembic is a second package, and `alembic_version` is a bookkeeping table in the
  user's file. Neither level of UC-14 changes it. The installer must package the
  revision files.
- The conversation store builds its queries with the tables of the ORM classes. No
  `Session` runs yet, so the relationships are declarations only.
- A file from before the first revision cannot upgrade.
- Removing a past feeling (UC-13-A2) deletes events, so a later replay replays what is
  left, not what happened.
- The `SpeechGate`, not the database, knows which `decision_factors` each kind of
  message needs (NFR-09), and the domain holds the unit and the table for each factor
  name.
- The database does not check the seqs and the fingerprint in a tombstone.
- Nothing checks the ERD against the ORM classes.
- The current code still opens the connection on the GUI thread.

**Neutral**

- The ranges of the temperament columns and the 1-to-10 importance scale are proposals
  that trial use sets (ADR 0004).

## Alternatives considered

**Keep numbered SQL files and SQLAlchemy Core.** No new package, and no bookkeeping
table. Rejected by the author, because the schema then has two definitions and needs a
self-check to keep them equal.

**Map the domain dataclasses to the tables.** No second class for each table. Rejected
because the ORM writes attributes, so a model could not stay frozen.

**Full event sourcing: every table a projection of the event log.** Perfect replay.
Rejected because correcting or deleting one item would mean rewriting events and
rebuilding projections, for the most common thing the user does with their memory.

**Two revisions: the old schema, then a redesign that copies conversations and
messages.** Upgrades the old file. Rejected because the old file held one empty
conversation, and each new file would build 13 tables only to drop them.

**JSON columns for the temperament, the explanation figures and the evidence.** Fewer
tables and columns. Rejected because the database could then check only that the text
is JSON, not that a value is in range or that an event exists.

**Integer keys everywhere.** Smaller and faster joins. Rejected because the current
tables already use UUID text, and a UUID exists before the write, so related rows can
be linked in one transaction.

**`metadata.create_all()`.** No revision files. Rejected because a fresh file and an
upgraded file would drift apart.
