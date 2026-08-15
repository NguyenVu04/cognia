# 1. Layered architecture with an event-driven core

- **Status:** Accepted
- **Date:** 2026-08-15
- **Deciders:** Nguyễn Duy Vũ
- **Supersedes:** —
- **Superseded by:** —

## Context

Cognia is a single-user desktop companion that runs all day on one Windows
machine. Its use case specification (COG-UCS-001) does not read like a list of
features. It reads like a list of promises, and almost all of them cut across
every use case at once:

- Seven base rules bind every use case, and no character may override them
  (C-04, FR-04).
- No proactive message may be sent without a complete explanation, and the check
  refuses rather than warns, in the build (NFR-10, UC-17).
- Every decision to speak must replay to an identical result over the same
  recorded input, so that two strategies can be compared fairly (NFR-14).
- If the AI model fails, everything that does not need it keeps working (NFR-09).
- Exactly three facts about the user may be read from the operating system
  (C-05, NFR-03).

None of these is a feature that can live in one place. Each is a property that
has to hold across all twenty use cases, including ones not yet written, and each
has to be **verifiable** rather than merely intended — the specification commits
to proving them by build check, system-call audit, and replay comparison.

Two further facts constrain the answer. The exclusions in section 5, restated in
the requirements table as FR-24, mean extensibility is an explicit anti-goal
rather than an unstated one: the list exists to close questions, not to leave
them open. And there is one developer, a demonstrable version due at the end of
phase 2, and no framework chosen yet.

## Decision

We build Cognia as a layered application with an event-driven core, and we
enforce the layering mechanically rather than by discipline.

- **Layers, one way.** Presentation, application services, domain, adapters.
  Dependencies point inward only, and an import in the reverse direction fails
  the build.
- **Ports belong to the domain.** The domain declares the interfaces it needs by
  capability — replying in character, whether the user is at the desk, the
  current time, storage, showing something — and adapters implement them. The
  data types on those ports are where the constraints live: the presence port
  carries exactly the three facts C-05 permits, so no code can ask for a fourth.
- **One ordered queue.** Events from outside — idle ticks, lock and unlock, the
  user opening or closing a session — enter a single bounded queue with one
  reader, are appended to a journal, and are handed to the domain in order.
- **One way out.** Every proactive message, including anything the companion
  shows rather than says, leaves through a single `SpeechGate`. It assembles the
  explanation NFR-10 requires and refuses to emit without one. No other component
  may reference the outbound port.
- **A pure domain.** No I/O and no ambient clock; time is injected. Given the same
  journal, the domain produces the same decisions.
- **An append-only decision journal.** What was observed, which threshold was
  crossed, what delayed the message, how much of the allowance was spent. UC-17
  reads from it and NFR-14 replays it.

This shape is independent of the framework, which has not been chosen.

## Consequences

**Positive**

- NFR-14 becomes a property of the structure rather than a feature to be built: a
  pure domain fed an ordered journal replays by construction.
- NFR-10 has a single choke point to guard, so the build check enforces one rule
  instead of policing an ever-growing list of call sites.
- NFR-09 becomes a table. Each use case names the ports it needs, and the
  degradation test is to disable an adapter and check the table still holds.
- C-05 is carried by a data type rather than by a rule someone has to remember,
  which reduces the code review NFR-03 asks for to reading one adapter.
- The exclusions in section 5 are enforced by absence. There is no mail port, so
  there is no way to read mail.

**Negative**

- More indirection. A change touching the screen, the domain and storage costs
  more files than a direct call would.
- The single reader serialises. A slow handler delays every event behind it, so
  domain work must stay short and all I/O must sit in adapters.
- The architecture tests are themselves code to maintain, and a rule that is
  subtly wrong blocks work while it is argued about.
- Domain purity forbids reading the clock anywhere inside it. This is easy to
  break by accident and is caught only because a test goes looking for it.
- The journal records observations about the user, so it is personal data under
  NFR-04 and must be reachable by UC-12, UC-13 and UC-14. Being an implementation
  detail does not exempt it.

**Neutral**

- Ports have to be defined before adapters, which is friction while the framework
  is undecided and a benefit once it is chosen.
- The domain is portable. Replacing the presentation layer, or adding a second
  operating system, does not touch it.

## Alternatives considered

**Microkernel, with capabilities as plugins.** Attractive because the model, the
presence source and the kinds of proactive message all look pluggable. Rejected
for two reasons. Extensibility is an explicit anti-goal here, so the cost of a
plugin contract, versioning and lifecycle is never repaid. More decisively, a
plugin able to load code into the process makes FR-04 and NFR-13 unenforceable:
"no character can switch this off" stops being true the moment a character can
arrive with code attached. Swappable providers are kept, but as separate
processes named in configuration — never as loaded code.

**A publish/subscribe bus throughout.** The natural reading of "event-driven",
and it would decouple the components further. Rejected because unordered or
parallel handlers destroy the determinism NFR-14 requires, and because a bus
multiplies the places a message can leave the system, which is exactly what the
single guarded exit in NFR-10 depends on. Events are kept at the boundary;
dispatch inside is a direct, ordered call.

**Plain layering, with the domain calling infrastructure directly.** The smallest
structure that still separates concerns, and the cheapest to write. Rejected
because NFR-09 and NFR-14 both need the domain to be substitutable and pure. A
domain that opens its own database connection and reads its own clock can neither
be replayed nor run with the model switched off.
