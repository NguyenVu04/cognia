# 6. The foreground application name in the event log

- **Status:** Proposed
- **Date:** 2026-10-30
- **Deciders:** Nguyễn Duy Vũ
- **Supersedes:** —
- **Superseded by:** —

## Context

COG-UCS-001 version 5.1 had a conflict between three of its parts.

- C-05 and NFR-02 kept the name of the foreground application only as minutes per
  application per hour of the day.
- UC-22 says that the companion decides from "which application they are in".
- NFR-13 needs each input to a decision in the recorded log, so that a replay matches.

The ERD already held a `foreground_app` event with an exact time, which C-05 did not allow.
One of the three had to give way.

## Decision

**We keep each change of foreground application in the event log, with its exact time, and
we change the specification.** Version 5.2 widens C-05, NFR-02 and NFR-03, and it adds the
recorded changes to UC-04 and UC-12.

- The event holds the application's file name and nothing else about it. A window title, a
  document name and a window position stay forbidden.
- `app_usage` still holds the hourly totals, and UC-24 reads them.
- An excluded application reports an empty name. The exclusion also deletes its totals and
  its `foreground_app` events (UC-04-A3).
- The events are personal data. UC-12 lists them, and UC-14 erases them.

## Consequences

**Positive**

- A decision can use the application at once, and a replay of it stays exact.
- The design is simple. One mechanism carries all presence facts.
- The ERD and the specification now agree.

**Negative**

- The disk now shows when the user changed applications, to the second. This is more sensitive
  than hourly totals, and it widens a privacy promise that the project made in version 5.0.
- The event log becomes a larger target for anyone who can read the file (ADR 0003 leaves it
  unencrypted, on purpose).
- A replay after an exclusion replays what is left.

**Neutral**

- NFR-02 is still checked by the same audit, with a wider list of what may be stored.

## Alternatives considered

**Keep the live name in memory only, and log hourly totals.** The application name would be a
hint for wording and never an input to a decision. C-05 would stay as it was, and replay would
stay exact. Rejected by the author, because decisions would see the application only up to the
last closed hour, which weakens UC-22.

**Log a category, such as `writing` or `comms`.** Decisions could use a category at once. Rejected
because a category is still a stored fact finer than an hour, so the specification must change
anyway. It also needs a table that maps each application to a category.
