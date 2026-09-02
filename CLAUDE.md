# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code
in this repository.

## Working agreement

These four rules outrank convenience. They apply to every task in this repository,
including ones the user describes as quick or trivial.

### Never guess

If a fact is not in the repository, in the prompt, or in tool output you have
actually read, you do not know it — ask.

- Do not infer a version, a path, a framework, an API shape, or the user's intent
  from a name, a filename, or a convention seen elsewhere. Read the file, or ask.
- Do not invent commands, flags, environment variables, or config keys. Every
  command you state must exist in this repository's task runner, scripts, or docs.
- Placeholder text (`TODO`, `<PLACEHOLDER>`, an empty stub) is a question to ask,
  not a blank to fill from imagination.

When the unknown does not block the work: do everything that does not depend on
it, state the assumption explicitly in the response, and continue. When proceeding
under a wrong assumption would be unsafe, destructive, or would waste the work
entirely — stop and ask before doing anything.

### Ask before "fixing" code the user supplied

When the user provides a script, a diff, or a file that does not meet the
standards in this document, do not silently rewrite it.

1. Name the specific rule it misses and the line it misses it on.
2. Ask one question per genuine ambiguity — not a questionnaire. If the deviation
   is unambiguous and mechanical, fix it and report it rather than asking.
3. Wait for the answer before restructuring, renaming, reformatting, or changing
   dependencies. Deviations are often deliberate.

Do the work that was asked for. Improvements you noticed but were not asked for
are reported, not applied.

### Always report what was done and changed

Every response that touched anything ends with a plain, factual account:

- **Files changed** — each path, and what changed in it, in one line each.
- **Verified** — the command actually run and its actual result. Not "tests
  should pass"; either the output, or an explicit "not run".
- **Not done** — anything skipped, blocked, or deliberately left out, and why.

Report failures as failures. A test that fails, a step that was skipped, and a
command that was never run are each stated plainly, with the output. Never
describe work as complete on the strength of having written the code.

### Hold the scope

Deliver exactly the requested scope — no silent widening, no silent narrowing. If
part of it turns out to be blocked, finish every other part in full and say
precisely what was left out and why. Scaling the work down is the user's call.

## Commands

From the repository root, via `Taskfile.yml`:

| Command | |
|---|---|
| `task` | list the available tasks |
| `task setup` | install dependencies into `desktop/.venv` |
| `task run` | run the application, installing dependencies first |
| `task run:quick` | run without re-checking dependencies |

The underlying commands, if you would rather run them from `desktop/`:

| Command | |
|---|---|
| `uv sync` | install dependencies |
| `uv add <package>` | add a dependency and update `uv.lock` |
| `uv run python -m src` | run the application |

Everything runnable lives in `desktop/`; the repository root holds documents only.

**There is no lint command and no test suite.** `desktop/tests/` is empty and no
linter, formatter, or test runner is configured — `docs/CONTRIBUTING.md` says the
same. Do not claim to have run one, and do not add tooling unless asked.

To inspect the interface without a display, set `QT_QPA_PLATFORM=offscreen` and
call `widget.grab().save(path)`; every screen renders headless.

## Architecture

`desktop/src/__main__.py` calls `src/app/application.py`, which creates the
`QApplication`, registers the vendored fonts, applies the style sheet, and
constructs the three surfaces — the main window, the companion window, and the
system-tray icon with its popup. It is the only module that knows about all
three; they communicate through Qt signals and never import each other.

**Only the presentation layer exists.** Today `src/ui/`, `src/app/`, `src/utils/`
and `src/resources/` hold code; `src/core/` and `src/infrastructure/` are empty by
intent. What is built is the [Cognia design document][design] made runnable: no
domain, no persistence, no AI, no reading of the operating system. Every response
to a click changes what is on screen and nothing else.

[design]: https://claude.ai/design/p/8d583ae3-f172-4466-a4b9-bcaa8f979c01

### Folders

| Folder | Responsibility |
|---|---|
| `app/` | Application initialization, configuration, and dependency management |
| `ui/windows/` | Main application windows |
| `ui/dialogs/` | Dialogs and modal windows |
| `ui/widgets/` | Custom and reusable `QWidget` components |
| `ui/views/` | Application screens and pages |
| `core/models/` | Domain models and data models |
| `core/ports/` | The interfaces the domain needs, stated without naming a provider |
| `core/services/` | Business logic and application services |
| `infrastructure/` | Database, REST APIs, filesystem, and external services |
| `resources/` | Icons, images, fonts, and QSS stylesheets |
| `utils/` | Logging and shared utility functions |
| `tests/` | Unit and integration tests |

### Dependency direction

One way only. ADR 0001 makes an import in the reverse direction a build failure,
not a shortcut.

| Layer | May import | Must never import |
|---|---|---|
| `ui/` | `PySide6`, `utils/`, `core/models/` | `infrastructure/`, `app/` |
| `core/` | the standard library only — it is pure, with time injected | `PySide6`, `ui/`, `infrastructure/` |
| `infrastructure/` | `core/` (it implements `core`'s ports) | `ui/`, `app/` |
| `app/` | everything; it wires the layers together | — (nothing imports `app/`) |
| `utils/` | the standard library | every other layer |

Three commitments from ADR 0001 bind any work that reaches past presentation: the
domain is pure with no ambient clock, so decisions replay identically (NFR-14);
every proactive message leaves through a single `SpeechGate` that refuses to emit
without a complete explanation (NFR-10); and events enter through one ordered,
journalled queue with one reader.

## Conventions

- **Scope is closed.** Section 5 of the specification, restated as FR-24, lists
  exclusions as *deliberately never*: task and reminder management, precise-time
  alarms, mail and calendar, acting on the user's behalf, cross-device sync,
  reading which application or window is open, and a companion with moods or
  needs. Adding one is a specification violation, not an improvement.
- **C-05 — three facts, no more.** The only things that may ever be read from the
  operating system are idle time, lock state, and presentation state. Never
  keystrokes, the screen, the clipboard, browsing history, or window identity.
  The port's data type is what enforces this; do not widen it.
- **Font sizes never appear in QSS.** Qt style sheets take whole pixels only and
  the design is built on fractional sizes (9.5, 12.5, 13.8, 14.5 …). Every size
  goes through `theme.font()`, which carries the fraction via `setPointSizeF`.
- **Colours come only from `src/ui/theme.py`.** `src/resources/qss/app.qss` carries
  `$TOKEN` placeholders that `theme.stylesheet()` substitutes. A literal hex
  anywhere else is a bug.
- **Scope every style sheet to its own widget.** A sheet set on a widget applies
  to all its descendants, so an unscoped `border-bottom` on a row underlines every
  label inside it. Subclass `widgets/surface.StyledWidget` or `Panel` and use
  `setRules()` / `addRules()`; a bare `QWidget` also ignores `background` and
  `border` unless `WA_StyledBackground` is set.
- **`box-shadow: 0 0 0 1px` becomes `border: 1px solid`**, with one pixel taken off
  each padding edge — a CSS ring costs no space and a Qt border does. `Panel` does
  this for you.
- **`src/ui/views/sample_data.py` is mockup copy, not domain data.** No other
  module under `src/ui/` may hard-code screen text. It is deleted whole when the
  domain arrives.
- **Commits.** [Conventional Commits](https://www.conventionalcommits.org/); the
  type decides the changelog group and, once there are releases, the version bump.
  Branch from `main` as `type/short-description`. Every pull request adds an entry
  under `Unreleased` in `docs/CHANGELOG.md`.
- **ADR before an architecturally significant change.** See `docs/adr/README.md`.

## Do not edit

| Path | Change it by |
|---|---|
| `desktop/src/resources/fonts/*` | Vendored Inter (OFL-1.1) and Phosphor Icons (MIT). Replace by re-downloading the release and its licence file together |
| `desktop/uv.lock` | `uv add` / `uv sync`, never by hand |
| `docs/USECASE_SPECIFICATION.html` | COG-UCS-001 v3.0, the source of record. Changing it needs a version bump in its section 1.1 and the approvals in 1.2 |
| `docs/adr/*.md` (accepted) | Write a new ADR that supersedes it; never edit an accepted one |

**There are no secrets and no `.env`.** Cognia has no account, no server, and holds
no credentials of its own (NFR-01, C-02). If a task appears to need a key, an
endpoint, or an outbound connection, that is a scope question — stop and ask.

## Before calling work done

1. `task run` has been **run**, not assumed. There is no lint or test command to
   run — say so rather than implying a suite passed.
2. The change does what was asked and nothing more.
3. The report from "Always report what was done and changed" is written, with the
   real command output and every skipped item named.
4. Any interface change has been looked at, screen by screen, against the design
   document — including the two overlays (paused, break nudge) and the first-run
   view, which are not reachable from the sidebar.
