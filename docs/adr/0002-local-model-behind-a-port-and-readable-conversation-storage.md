# 2. A local model behind a port, and conversations in readable SQLite

- **Status:** Proposed
- **Date:** 2026-09-02
- **Deciders:** Nguyễn Duy Vũ
- **Supersedes:** —
- **Superseded by:** —

## Context

Until now Cognia was the design made runnable: `src/core/` and
`src/infrastructure/` were empty, the only dependency was PySide6, and the Send
button on the Companion screen was connected to nothing. FR-13 — hold a
conversation in character — needs three things that do not exist: a model to
answer, somewhere for the conversation to live, and a way to do the first
without freezing the second.

Several promises bear on how those are built. NFR-01 and C-02 allow no account,
no server, and no outbound connection the user did not switch on. NFR-04 keeps
the user's data on their disk with no second copy. The specification is
unusually direct about the *shape* that storage should take: "local storage that
cannot be read is worth no more than storage on someone else's server". NFR-09
requires that everything not needing the model keeps working when the model
fails, and NFR-06 forbids a blank pause while a reply is composed.

ADR 0001 already settled the structure — ports belong to the domain, adapters
implement them, dependencies point inward. What it did not settle is which
libraries are allowed to exist, where they may live, and what the conversation
is written into.

## Decision

**LangChain and LangGraph live only in `src/infrastructure/`.** `OllamaAgent`
implements a domain port, `Replier`. The graph is a `StateGraph` with a single
model node. That is ceremony for one call today, and deliberately so: memory
extraction (FR-14), the in-conversation adjustment (FR-15) and any tool the
companion is ever given become nodes and edges rather than a rewrite of the
call site. Nothing above `infrastructure/` knows the library exists.

**Ports get their own folder, `src/core/ports/`.** ADR 0001 says ports belong to
the domain; the folder table in `CLAUDE.md` listed only `models/` and
`services/`. The table gains a row rather than the ports being filed somewhere
they do not belong.

**The model is Ollama on localhost, named in configuration.** `qwen3.5:2b` at
`http://localhost:11434`, in `src/app/config.py`, overridable by a `config.json`
the user may write. ADR 0001 keeps swappable providers named in configuration
rather than loaded as code, and this is that.

**Conversations are stored in plain SQLite tables that Cognia owns.** Two
tables, `conversations` and `messages`, with ordinary columns — no blobs, no
serialised framework state. `sqlite3 cognia.sqlite3 "SELECT * FROM messages"` is
a supported way to read your own conversations. LangGraph's checkpointer is
**not** used: it would store the same history as msgpack blobs, which is the
opaque storage the specification argues against, and a second copy of the truth
besides. The graph is stateless per turn; history is loaded from the store and
passed in.

**Replies are streamed on a worker thread.** `ChatWorker` lives in `src/app/`,
because it touches both Qt and `infrastructure/` and `ui/` may import neither.
The typing indicator the design already drew is shown on send and hidden at the
first token, which is NFR-06 satisfied by a widget that previously had no
trigger.

**Tracing is switched off in the program, not left to the environment.**
`langsmith` is a hard dependency of `langchain-core`, so it is installed
whichever LangChain packages are chosen, and it enables itself from an
environment variable. `src/app/local_only.py` sets those variables to `false`
before the first LangChain import, so NFR-01 is a property of Cognia rather than
of the machine it happens to run on.

**`deepagents` is not adopted.** It requires `langchain-anthropic` and
`langchain-google-genai` — two cloud model SDKs — as mandatory dependencies. It
may be revisited if and when its sub-agents or skills are actually needed *and*
those SDKs can be excluded; wanting the library is not on its own a reason to
put cloud clients in a local-only application.

**No `SpeechGate` here.** NFR-10 governs *proactive* messages. A reply the user
asked for is not proactive, so it does not pass the gate, and the ordered event
queue and decision journal are likewise untouched: they serve observation, which
this change does not begin.

## Consequences

- FR-13 becomes real, and NFR-06, NFR-08 and NFR-09 acquire implementations that
  can be tested rather than intentions. The traceability matrix can move them off
  "Not started".
- The dependency tree grows from one package to roughly forty transitively.
  `langsmith`, `httpx` and `requests` are now installed — libraries whose purpose
  is to talk to the network — inside an application that promises not to. The
  hard-disable above is why that is tolerable; it is not why it is comfortable,
  and NFR-01's verification by network capture matters more than it did.
- `MessageRow` now takes a `core.models.Message`, so the bubbles no longer read
  mockup data. `sample_data.MESSAGES` is dead. The rest of `sample_data` is still
  read by five other views, so the module cannot yet be "deleted whole" as its
  docstring promises.
- **A conversation picker was added to the Companion header, and it is not in the
  design document.** Conversations now outlive the window, so there had to be
  some way back to an earlier one. It reuses the `TrayMenu` popup pattern rather
  than a native `QMenu`. This is a deliberate step beyond the drawn design and
  should be reviewed against it.
- The character is still `sample_data.CHARACTERS[0]`, and the system prompt is
  assembled in `app/`. FR-02 will move both; until then the companion's identity
  is mockup copy.
- The first threading in the repository now exists, so "which thread is this on"
  becomes a question every future contributor has to answer. The store is opened
  with SQLite's same-thread check left on so that getting it wrong fails loudly.
- Nothing writes the `note` column. The "Stored — you told me" chip the design
  draws stays unused until FR-14.

## Alternatives considered

**LangGraph's `SqliteSaver` as the only store.** The least code, and the
idiomatic way to give a LangGraph agent memory. Rejected on the specification's
own terms: the history would be msgpack inside a `checkpoints` table, unreadable
without the application, which is the thing NFR-04's supporting argument
explicitly calls worthless. A readable mirror alongside it was also considered
and rejected as two sources of truth for one fact.

**A tool-calling ReAct agent from the start.** `qwen3.5:2b` does advertise
`tools`. Rejected because there are no tools to give it — an empty loop is
structure without content, and small models call tools unreliably enough that
the first tool should arrive with a reason and a test, not ahead of both.

**Disabling the model's thinking.** `qwen3.5:2b` supports it, and turning it off
would reach the first token sooner. Kept on, with the reasoning discarded: the
answers are better, and the typing indicator already covers the wait honestly.
The reasoning arrives separately from the answer, so hiding it costs nothing and
no text has to be stripped.

**Running the model call on the GUI thread.** Rejected outright; a 2B model
takes seconds and the window would stop painting, which NFR-06 forbids in
spirit and NFR-07 in figures.
