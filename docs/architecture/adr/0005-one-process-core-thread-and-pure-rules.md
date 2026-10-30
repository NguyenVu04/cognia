# 5. One process, one core thread, pure rules, and a next wake time

- **Status:** Proposed
- **Date:** 2026-10-30
- **Deciders:** Nguyễn Duy Vũ
- **Supersedes:** —
- **Superseded by:** —

## Context

ADR 0001 sets the layers, one ordered queue with one reader, and a pure domain. It does
not say what runs where. Four questions stayed open:

- How many processes does Cognia need?
- Which thread reads the queue, and which thread holds the database?
- How does the domain reach the outside, so that a replay needs no model and no database?
- How does time reach the domain?

Today the database connection is on the GUI thread, and `synchronous=FULL` makes each
commit wait for the disk (NFR-08). Nothing reads the operating system yet.

NFR-14 asks for an identical replay. NFR-07 asks for almost no cost while idle. NFR-05
asks for a pause in under one second. [`ARCHITECTURE.md`](../ARCHITECTURE.md), D-01, D-03,
D-09 and D-10, gives the full comparison.

## Decision

**One application process.** `Cognia.exe` holds the GUI, the core and the adapters. The
model servers and the Chromium render process are child processes. No IPC exists between
the parts of Cognia.

**A core thread reads the queue and holds the database.** The queue is a bounded
`queue.Queue`. The core thread is the only reader and the only thread that touches SQLite.
The GUI thread sends commands and receives frozen dataclasses. A model thread runs one job
at a time. A sampler thread reads Windows once each second.

**Pure rules and services.** A rule is a pure function with this shape:

```text
step(state, event, settings) -> state, effects, next_wake
```

A rule reads no clock, does no I/O and calls no port. A service loads data through ports,
calls rules, writes the result, and starts the effects. `rules.py` and
`<feature>_service.py` are separate files in each feature.

**One item, one transaction.** The core thread appends the event, runs the rules, writes
the rows, and commits. Only then does it start outward effects. Nothing reaches the screen
before its record is on disk.

**Change events and a next wake time.** The sampler reports changes only. Each step returns
the next time that a rule can change its answer. The core thread waits on the queue with a
timeout that ends at that time. When the time arrives, the core thread writes a `timer`
event. The event's own time is the only clock that a rule sees.

**Input closure.** The rules read only the event log and rows that never change. Each user
action that can change a decision is also an event. Section 6.4 of `ARCHITECTURE.md` gives
the closed set.

## Consequences

**Positive**

- A replay is a fold over the log. It needs no database, no fakes and no model (NFR-14).
- A slow commit cannot stop the drawing.
- The core thread sleeps between events, which NFR-07 needs.
- A decision has an exact time, not a time on a one-minute grid.

**Negative**

- A Python crash stops the GUI and the core together. Committed data survives.
- Each UI read is asynchronous, so views need a waiting state.
- Each rule must compute its next wake time, which is harder to reason about than a tick.
- State must fit in memory, so learning keeps small totals and not whole events.
- The core thread folds the whole log at start, and the cost grows with the log. A snapshot
  table is the upgrade if a measurement demands it.
- A power failure between a commit and its effect leaves a record of a message that nobody
  saw. The design accepts this, because the reverse order breaks NFR-10.

**Neutral**

- Ports stay in the domain, as ADR 0001 says. Services call them, and rules do not.
- The current code does not follow this record yet.

## Alternatives considered

**A separate core process and a UI process.** A GUI crash would leave the core alive. Rejected
because the tray and the companion are always present, so both processes always run, and an
IPC contract adds cost for one client.

**A local WebSocket server.** Open-LLM-VTuber has this shape. Rejected because it adds a port to
protect, and it serves many clients where Cognia has one.

**A second, read-only connection on the GUI thread.** Views would stay simple. Rejected because a
slow query would still stop the GUI, and it changes ADR 0003.

**All work on the GUI thread.** The least code. Rejected because each commit would run on the
thread that draws.

**Domain services that call ports inside the rules.** Close to the wording of ADR 0001. Rejected
because a replay would need a fake for each port, and I/O could enter a rule unnoticed.

**A tick in the log.** Simple rules. Rejected because it adds about 525,000 rows each year and a
disk write each minute.

**A tick that is not logged.** Rejected because a replay would have to invent the ticks, so it
would differ after a sleep.
