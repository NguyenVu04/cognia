# 2. A local model behind a port, and conversations in readable SQLite

- **Status:** Proposed
- **Date:** 2026-09-02
- **Revised:** 2026-10-24 — the model ships with the application as a llama.cpp
  server instead of a separately installed Ollama (COG-UCS-001 v4.0, NFR-14)
- **Revised:** 2026-10-25 — English only; the Vietnamese option is removed
  (COG-UCS-001 v5.0, C-06)
- **Revised:** 2026-10-30 — LangChain and LangGraph are removed, the server ships in
  two builds, and ports move to `src/domain/ports/`
  ([`ARCHITECTURE.md`](../ARCHITECTURE.md), D-02, D-06, D-13)
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
no server, and no outbound connection. NFR-03 keeps
the user's data on their disk with no second copy. The specification is
unusually direct about the *shape* that storage should take: "local storage that
cannot be read is worth no more than storage on someone else's server". NFR-08
requires that everything not needing the model keeps working when the model
fails, and NFR-05 forbids a blank pause while a reply is composed.

Version 4.0 of the specification adds two more. NFR-14 requires the model and
everything needed to run it to ship inside the installer: no separate runtime to
install, nothing downloaded at first run. NFR-10 counts on that — five minutes
from a finished installation to a first conversation, with no second program.
C-06 makes the companion speak English, including the fixed wording it uses when
the model cannot answer. Version 4.0 also offered Vietnamese on request; version
5.0 removed it.

ADR 0001 already settled the structure: ports belong to the domain, adapters
implement them, dependencies point inward, and swappable providers run as
separate processes named in configuration, never as loaded code. What it did not
settle is which libraries are allowed to exist, where they may live, how the
model is run, and what the conversation is written into.

## Decision

**The adapter calls the server directly, with no LangChain or LangGraph.** The
adapter implements the domain ports `Replier`, `Interpreter` and `Embedder`. Each
step of a turn must pass the event queue (ADR 0005), so the services own the order
of the steps and a graph has no job left. Memory extraction (FR-14), commitments
(FR-29) and the in-conversation adjustment (FR-15) are fields of one structured
interpretation call. Nothing above `infrastructure/` knows how the call is made.

**Ports get their own folder, `src/domain/ports/`.** ADR 0001 says ports belong to
the domain. One folder lets a reviewer read every port in one place.

**The model is a llama.cpp server that ships with Cognia.** The installer
carries `llama-server.exe` in two builds, Vulkan and CPU, and the GGUF model files.
Cognia starts the server as a child process when it starts, bound to `127.0.0.1` on a
free port it chooses, with the model file's path, `--offline`, `--no-webui`, a new
`--api-key` for each start, and no option that downloads anything. It tries the
Vulkan build first and uses the CPU build if that fails. The child is
placed in a Windows job object, so it ends with Cognia even when Cognia crashes
rather than being left running. Paths to the binary and the model file are
named in configuration, relative to the installation folder, and overridable by
a `config.json` the user may write — ADR 0001's provider-as-configured-process,
with the process now Cognia's to start and stop.

**Which model ships is not decided here.** It is chosen by measurement, not by
this record: it must hold a character in English (A-02, C-06),
and its size sets the figures NFR-14 leaves open. `qwen3.5:2b`, the model this
record first named, is the first candidate to measure. Whether its GGUF weights
may be redistributed inside an MIT-licensed installer has not been confirmed,
and has to be before it ships.

**The adapter talks to the server's HTTP API with `httpx`.** `langchain-ollama`,
`langchain-core` and `langgraph` are removed. A small client in
`src/infrastructure/ai/` reads the server's streamed reply, and it uses the
`json_schema` option for structured calls. `httpx` becomes a direct dependency
rather than a transitive one. The server's OpenAI-compatible endpoint is **not**
reached through the `openai` SDK, because that is a cloud client.

**Conversations are stored in plain SQLite tables that Cognia owns.** Two
tables, `conversations` and `messages`, with ordinary columns — no blobs, no
serialised framework state. `sqlite3 cognia.sqlite3 "SELECT * FROM messages"` is
a supported way to read your own conversations. History is loaded from the store and passed in for each turn.

**Replies are streamed on a model thread.** The model thread runs one job at a time
(ADR 0005), so no other thread waits for the model.
The typing indicator the design already drew is shown on send and hidden at the
first token, which is NFR-05 satisfied by a widget that previously had no
trigger.

**The companion speaks English, and so does its fallback wording.** The system
prompt asks for English (C-06). The plain sentences the adapter returns when the
model cannot answer (UC-09-E1) are kept in English, because C-06 covers them too.
There is no language setting to read.

**No tracing library remains.** `langsmith` was a hard dependency of
`langchain-core`. With that package gone, `src/app/local_only.py` has no job, and it
goes with the same change.

**No `SpeechGate` here.** NFR-09 governs *proactive* messages. A reply the user
asked for is not proactive, so it does not pass the gate.

## Consequences

- FR-13 becomes real, and NFR-05, NFR-07 and NFR-08 acquire implementations that
  can be tested rather than intentions. The traceability matrix can move them off
  "Not started".
- NFR-10 and NFR-14 become attainable: the user installs one thing, and the first
  run needs no network. UC-01-E1 shrinks to two failures Cognia can name
  precisely — a damaged installation, or a machine below the stated minimum.
- The installer grows by the server binary and the model file. How much is not
  measured, because the model is not chosen; NFR-14 leaves the figure open for
  exactly this reason.
- Cognia now owns a second process. Starting it, choosing its port, noticing that
  it died, and saying so plainly (UC-09-E1) are Cognia's code rather than the
  user's chore. A server that fails to start leaves memory, sessions and pausing
  working, as NFR-08 requires.
- The dependency tree loses LangChain, LangGraph, `langsmith` and the `ollama`
  client. It keeps `httpx`, and only `src/infrastructure/ai/` may use it. NFR-01's
  network capture now also covers the child processes.
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
- The code still runs against Ollama and LangGraph (`OllamaAgent`, `OLLAMA_*` in
  `src/config.json`, and `ChatWorker`). This revision describes where it is going, not
  where it is.

## Alternatives considered

**LangChain and LangGraph in the adapter, as this record first decided.** One
`StateGraph` with a model node, and a small `BaseChatModel` of its own. Graph nodes
would stay available. Rejected because the graph has one node, each step must pass the
queue, and it costs start-up time. One cold run on the author's machine, with each
package in its own process, took 1232 ms for `langgraph.graph` and 665 ms for
`langchain_core.messages`, against the 2 seconds of NFR-04. It also keeps a tracing
library in an application that promises no outbound traffic.

**`deepagents`.** It requires two cloud model SDKs as mandatory dependencies. Rejected
for a local-only application.

**A separately installed Ollama on localhost.** This record's first decision:
`qwen3.5:2b` at `http://localhost:11434`, which the user installs and pulls
themselves. Replaced because NFR-14 forbids a second installation and a
first-run download, and NFR-10 cannot be met with one.

**Ollama itself, shipped inside the installer.** The smallest change: the
`langchain-ollama` adapter would stay as it is. Not chosen. It would carry a
model registry, a pull mechanism and a daemon of its own that Cognia would never
use, inside an application that is meant to run one fixed model file.

**`llama-cpp-python`, with the model loaded into Cognia's own process.** No child
process to manage. Rejected because ADR 0001, which is accepted, keeps providers
as separate processes named in configuration and never as loaded code, and
because a model failure inside the process would take down the parts NFR-08
requires to keep working.

**The server's OpenAI-compatible API through an OpenAI client.** The least code
for the adapter. Rejected for the same reason as `deepagents`: it makes a cloud
client a dependency of a local-only application.

**LangGraph's `SqliteSaver` as the only store.** The least code, and the
idiomatic way to give a LangGraph agent memory. Rejected on the specification's
own terms: the history would be msgpack inside a `checkpoints` table, unreadable
without the application, which is the thing NFR-03's supporting argument
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
takes seconds and the window would stop painting, which NFR-05 forbids in
spirit and NFR-06 in figures.
