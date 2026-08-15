# Contributing to Cognia

Thanks for taking the time. This document covers how to get set up, what a good
change looks like here, and what happens after you open a pull request.

Found a security problem? Do not open an issue — follow [SECURITY.md](SECURITY.md).

> [!NOTE]
> There is no application code yet. This repository holds the use case
> specification, the architecture decision records, and the project documents. Until
> phase 1 of the [roadmap](../README.md#roadmap) starts, every contribution is a
> change to a document — which does not make it a small contribution: a wrong claim
> in the specification is more expensive to fix later than a wrong line of code.

## Before you start

- **Corrections and small fixes** — a factual error, a broken link, a contradiction
  between two documents: open a pull request directly.
- **New features or behaviour changes** — open an issue first so we can agree the
  approach. Read section 5 of the specification before you do, because the scope is
  deliberately closed and most of the obvious suggestions are already answered there.
- **Architecturally significant changes** — write an ADR first. See
  [adr/README.md](adr/README.md).

### What will be declined

Section 5 of [the specification](USECASE_SPECIFICATION.html) lists exclusions marked
**deliberately never**, and FR-24 restates them as a requirement so the question is
not re-asked. A proposal to add task management, reminders, precise-time alarms, mail
or calendar integration, acting on the user's behalf, cross-device sync, reading which
window is open, or a companion with needs and moods will be closed with a pointer to
the row that covers it. This is not a judgement about the idea. It is that the value
of that list depends entirely on it staying closed.

Two exclusions are resourcing decisions rather than positioning ones, and are open to
discussion: generating an appearance, and macOS and Linux builds.

## Development environment

```bash
git clone https://github.com/NguyenVu04/cognia.git
```

There is nothing to install: no dependencies, no build, no git hooks. Confirm you have
what you need by opening `docs/USECASE_SPECIFICATION.html` in a browser — it is a
single self-contained file and needs no server.

When there is application code, this section will name the setup command and the
command that proves it worked. Until then, the honest answer is that there is none.

## Making a change

### Branches

Branch from `main`, named `type/short-description` — the same type you would use in
the commit subject, for example `docs/fix-adr-index` or `fix/session-close-timing`.

### Commits

We use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Commit
subjects look like:

```
docs(spec): correct the storage location in the references table
```

Accepted types: `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, `chore`.

The type is load-bearing rather than decorative: it decides which
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) group the entry lands in, and
once there are releases it drives the version bump. A change that adds behaviour is
`feat` even if it is three lines; a change that only moves code is `refactor` even if
it is three hundred.

Mark a breaking change with `!` after the type and a `BREAKING CHANGE:` footer saying
what a user has to do about it.

### Before you push

There is no lint command and no test suite yet, so there is nothing to run. What is
checked by reading, and what a reviewer will check:

- every claim in a document is traceable to the specification, an ADR, or something in
  the repository — not to a reasonable assumption;
- the documents still agree with each other. The specification, the ADRs, the README
  and this file cross-reference heavily, and a change to one usually needs a change to
  another;
- no template placeholder was reintroduced:

```bash
grep -rn '<[A-Z][A-Z0-9_]*>' README.md docs/*.md docs/adr/*.md
```

That command must print nothing.

## Pull requests

A pull request is ready for review when:

- [ ] it does one thing, and the description says what and why;
- [ ] user-facing changes are documented — README, the specification, or both;
- [ ] `docs/CHANGELOG.md` has an entry under `Unreleased`;
- [ ] breaking changes are labelled as such and explain the migration;
- [ ] no secret, credential, or personal data appears in the diff.

Once there is code, two more apply: tests cover the new behaviour and the suite
passes, and coverage stays at or above the floor — which will be set with the first
test suite rather than promised in advance here.

Link the issue it closes. Draft pull requests are welcome for early feedback.

### Review

| | |
|---|---|
| **First response** | Usually within a week. This is a one-person project run alongside academic work, and that is a realistic expectation rather than a service level |
| **Approvals needed** | One, from Nguyễn Duy Vũ. There is no second maintainer and no `CODEOWNERS` file |
| **Merge method** | Squash, so `main` keeps one commit per change |

Reviewers look for correctness, fit with the specification, and whether the change
survives the questions in section 5. If a review stalls, say so on the pull request,
or email nguyenvu04.work@gmail.com.

## Releases

Nothing has been released. The first release will be **0.1.0**, at the end of phase 1
of the [roadmap](../README.md#roadmap) — a character with a memory, usable every day.
There is no fixed cadence: a release happens when a phase is complete, not on a date.

Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html); see the
versioning section of the [README](../README.md#versioning-and-compatibility) for what
the version contract covers.

## Code of conduct

Be civil and assume good faith. There is no separate code of conduct document, because
there is one maintainer and a document nobody enforces is worse than none. Report
unacceptable behaviour to nguyenvu04.work@gmail.com.

## Questions

Open an issue at https://github.com/NguyenVu04/cognia/issues, or email
nguyenvu04.work@gmail.com.
