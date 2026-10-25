# 2. A local model behind a port, and conversations in readable SQLite

- **Status:** Proposed
- **Date:** 2026-09-02
- **Revised:** 2026-10-24 — the model ships with the application as a llama.cpp
  server instead of a separately installed Ollama (COG-UCS-001 v4.0, NFR-15)
- **Revised:** 2026-10-25 — English only; the Vietnamese option is removed
  (COG-UCS-001 v5.0, C-06)
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

Version 4.0 of the specification adds two more. NFR-15 requires the model and
everything needed to run it to ship inside the installer: no separate runtime to
install, nothing downloaded at first run. NFR-11 counts on that — five minutes
from a finished installation to a first conversation, with no second program.
C-06 makes the companion speak English, including the fixed wording it uses when
the model cannot answer. Version 4.0 also offered Vietnamese on request; version
5.0 removed it.

ADR 0001 already settled the structure — ports belong to the domain, adapters
implement them, dependencies point inward, and swappable providers run as
separate processes named in configuration, never as loaded code. What it did not
settle is which libraries are allowed to exist, where they may live, how the
model is run, and what the conversation is written into.

## Decision

**LangChain and LangGraph live only in `src/infrastructure/`.** The adapter
implements a domain port, `Replier`. The graph is a `StateGraph` with a single
model node. That is ceremony for one call today, and deliberately so: memory
extraction (FR-14), commitments (FR-29), the in-conversation adjustment (FR-15)
and any tool the companion is ever given become nodes and edges rather than a
rewrite of the call site. Nothing above `infrastructure/` knows the library
exists.

**Ports get their own folder, `src/core/ports/`.** ADR 0001 says ports belong to
the domain; the folder table in `CLAUDE.md` listed only `models/` and
`services/`. The table gains a row rather than the ports being filed somewhere
they do not belong.

**The model is a llama.cpp server that ships with Cognia.** The installer
carries `llama-server.exe` and one GGUF model file. Cognia starts the server as a
child process when it starts, bound to `127.0.0.1` on a free port it chooses,
with the model file's path and no option that downloads anything. The child is
placed in a Windows job object, so it ends with Cognia even when Cognia crashes
rather than being left running. Paths to the binary and the model file are
named in configuration, relative to the installation folder, and overridable by
a `config.json` the user may write — ADR 0001's provider-as-configured-process,
with the process now Cognia's to start and stop.

**Which model ships is not decided here.** It is chosen by measurement, not by
this record: it must hold a character in English (A-02, C-06),
and its size sets the figures NFR-15 leaves open. `qwen3.5:2b`, the model this
record first named, is the first candidate to measure. Whether its GGUF weights
may be redistributed inside an MIT-licensed installer has not been confirmed,
and has to be before it ships.

**The adapter talks to the server's HTTP API with `httpx`, through a small
LangChain chat model of its own.** `langchain-ollama` is removed. A minimal
`BaseChatModel` subclass in `src/infrastructure/ai/` implements streaming
against the server, so the graph and its token streaming are unchanged above
it. `httpx` becomes a direct dependency rather than a transitive one. The
server's OpenAI-compatible endpoint is **not** reached through `langchain-openai`
or the `openai` SDK: those are cloud clients, and this record already refused
`deepagents` for making cloud SDKs mandatory.

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

**The companion speaks English, and so does its fallback wording.** The system
prompt asks for English (C-06). The plain sentences the adapter returns when the
model cannot answer (UC-09-E1) are kept in English, because C-06 covers them too.
There is no language setting to read.

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
- NFR-11 and NFR-15 become attainable: the user installs one thing, and the first
  run needs no network. UC-01-E1 shrinks to two failures Cognia can name
  precisely — a damaged installation, or a machine below the stated minimum.
- The installer grows by the server binary and the model file. How much is not
  measured, because the model is not chosen; NFR-15 leaves the figure open for
  exactly this reason.
- Cognia now owns a second process. Starting it, choosing its port, noticing that
  it died, and saying so plainly (UC-09-E1) are Cognia's code rather than the
  user's chore. A server that fails to start leaves memory, sessions and pausing
  working, as NFR-09 requires.
- The dependency tree loses `langchain-ollama` and its `ollama` client, and keeps
  `langsmith`, `httpx` and `requests` — libraries whose purpose is to talk to the
  network — inside an application that promises not to. The hard-disable above is
  why that is tolerable; it is not why it is comfortable, and NFR-01's
  verification by network capture matters more than it did. The capture now also
  covers the child process.
- How the server separates the model's reasoning from its answer has to be
  verified against the build that ships. The behaviour below under "Disabling the
  model's thinking" was verified against Ollama, and does not carry over by
  assumption.
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
- The code still runs against Ollama (`OllamaAgent`, `OLLAMA_*` in
  `src/config.json`). This revision describes where it is going, not where it is.

## Alternatives considered

**A separately installed Ollama on localhost.** This record's first decision:
`qwen3.5:2b` at `http://localhost:11434`, which the user installs and pulls
themselves. Replaced because NFR-15 forbids a second installation and a
first-run download, and NFR-11 cannot be met with one.

**Ollama itself, shipped inside the installer.** The smallest change: the
`langchain-ollama` adapter would stay as it is. Not chosen. It would carry a
model registry, a pull mechanism and a daemon of its own that Cognia would never
use, inside an application that is meant to run one fixed model file.

**`llama-cpp-python`, with the model loaded into Cognia's own process.** No child
process to manage. Rejected because ADR 0001, which is accepted, keeps providers
as separate processes named in configuration and never as loaded code, and
because a model failure inside the process would take down the parts NFR-09
requires to keep working.

**The server's OpenAI-compatible API through `langchain-openai`.** The least code
for the adapter. Rejected for the same reason as `deepagents`: it makes a cloud
client a dependency of a local-only application.

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
Under Ollama the reasoning arrived separately from the answer, so hiding it cost
nothing and no text had to be stripped; with the llama.cpp server this is to be
re-verified, as noted above.

**Running the model call on the GUI thread.** Rejected outright; a 2B model
takes seconds and the window would stop painting, which NFR-06 forbids in
spirit and NFR-07 in figures.
