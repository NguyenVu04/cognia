# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

No version has been released. Until there is one, what changes in this repository is
the specification and the decisions taken from it, so that is what is recorded below.
The first release will be **0.1.0**, at the end of phase 1: a character with a memory,
usable every day.

The specification keeps its own revision history, at a coarser grain and with the
reasoning attached, in section 1.1 of
[`USECASE_SPECIFICATION.html`](USECASE_SPECIFICATION.html). Where the two disagree
about what happened, that section is the record.

## [Unreleased]

### Added

- **The companion answers.** The Companion screen holds a real conversation: what the
  user types goes to a model running on their own machine through Ollama, and the reply
  streams back into the bubble a word at a time. The "writing…" indicator the design
  had drawn but never shown now appears on send and gives way to the first words
  (FR-13, NFR-06).
- **Conversations are kept, and can be read.** Two plain SQLite tables in the user's
  data directory, written as they are said and reopened on launch. No blobs and no
  framework's private format: `sqlite3 cognia.sqlite3 "SELECT * FROM messages"` is a
  supported way to read your own conversations (NFR-04, NFR-08).
- A conversation picker in the Companion header, for reaching an earlier conversation
  or starting another. This control is not in the design document; see ADR 0002.
- The first domain and adapter code. `core/models/` holds `Message` and `Conversation`;
  the new `core/ports/` holds the two interfaces they are used through; `infrastructure/`
  holds the SQLite store and the LangGraph agent that implement them.
- ADR 0002: a local model behind a port, and readable conversation storage — LangChain
  and LangGraph confined to `infrastructure/`, plain SQLite over a LangGraph
  checkpointer, and hosted tracing switched off in the program rather than left to the
  environment.
- Use case specification COG-UCS-001, twenty use cases, seven base rules, twenty-eight
  functional and fourteen non-functional requirements, with a traceability matrix.
  Status: draft, awaiting approval by the supervising lecturer and the review panel.
- ADR 0001: a layered architecture with an event-driven core — a pure domain, one
  ordered event queue, ports owned by the domain, and a single `SpeechGate` that
  refuses to emit a proactive message without a complete explanation.
- Project README, describing what Cognia is, what it deliberately will never do, how
  each promise is to be verified, and what has and has not been built.
- Contributing guide, security policy, and this changelog.

### Changed

- **The companion became visible** (specification 3.0). It is drawn on the desktop as
  a character rather than living behind a tray icon, which gave it an appearance that
  version 2.0 had explicitly denied it. A seventh base rule, BR-07, puts movement
  under the same limits as speech, and NFR-07 split into two figures because a
  companion on screen costs what a hidden one does not.
- **The product was repositioned from a reminder tool to a desk companion**
  (specification 2.0), and reissued in English. The work session replaced the break
  reminder as the core interaction, and task management, reminders, precise-time
  alarms, mail and calendar integration moved from "later phase" to deliberately
  never.

[Unreleased]: https://github.com/NguyenVu04/cognia/commits/main
