<!--
  CONTRIBUTING TEMPLATE
  =====================
  Copy to your project root as CONTRIBUTING.md. GitHub surfaces it when someone
  opens an issue or a pull request.

  Same conventions as README.template.md: replace every <PLACEHOLDER>, resolve
  every marker, delete every GUIDANCE comment and this block.

      grep -n '<[A-Z][A-Z0-9_]*>' CONTRIBUTING.md      # must return nothing
-->

# Contributing to <PROJECT_NAME>

Thanks for taking the time. This document covers how to get set up, what a good
change looks like here, and what happens after you open a pull request.

Found a security problem? Do not open an issue — follow [SECURITY.md](SECURITY.md).

## Before you start

- **Bugs and small fixes** — open a pull request directly.
- **New features or behaviour changes** — open an issue first so we can agree the
  approach before you spend time on it.
- **Architecturally significant changes** — write an ADR first. See
  [docs/adr/README.md](docs/adr/README.md).

## Development environment

```bash
git clone <REPOSITORY_URL>
cd <PROJECT_DIRECTORY>
<SETUP_COMMAND>
```

This installs dependencies and the git hooks. Confirm it worked:

```bash
<VERIFY_COMMAND>
```

## Making a change

### Branches

Branch from `<DEFAULT_BRANCH>`, named `<BRANCH_NAMING_CONVENTION, e.g. type/short-description>`.

### Commits

<!-- GUIDANCE: If you use Conventional Commits, say so and list the types you
     actually accept — a generic link leaves people guessing. The convention is
     load-bearing if it drives your changelog or version bumps; say so if it does. -->

We use <COMMIT_CONVENTION>. Commit subjects look like:

```
<COMMIT_EXAMPLE, e.g. feat(api): add pagination to the search endpoint>
```

Accepted types: <COMMIT_TYPES, e.g. feat, fix, docs, refactor, test, build, ci, chore>.

<COMMIT_CONVENTION_CONSEQUENCE, e.g. Release notes and version bumps are generated
from these, so the type and scope matter.>

### Before you push

```bash
<LINT_COMMAND>
<TEST_COMMAND>
```

Both run again in CI, but failing locally first is faster for everyone.

## Pull requests

A pull request is ready for review when:

- [ ] it does one thing, and the description says what and why;
- [ ] tests cover the new behaviour, and the suite passes;
- [ ] coverage stays at or above <COVERAGE_THRESHOLD>%;
- [ ] user-facing changes are documented — README, API reference, or both;
- [ ] `CHANGELOG.md` has an entry under `Unreleased`;
- [ ] breaking changes are labelled as such and explain the migration;
- [ ] no secret, credential, or customer data appears in the diff.

Link the issue it closes. Draft pull requests are welcome for early feedback.

### Review

| | |
|---|---|
| **First response** | <REVIEW_SLA, e.g. within 2 business days> |
| **Approvals needed** | <NUMBER_OF_APPROVALS>, including a [code owner](.github/CODEOWNERS) |
| **Merge method** | <MERGE_METHOD, e.g. squash> |

Reviewers look for correctness, tests, and fit with the existing design. If a
review stalls, <ESCALATION_CONTACT>.

<!-- REQUIRED-IF: the project requires a Developer Certificate of Origin or a
     Contributor License Agreement. Delete otherwise. -->
### Sign-off

Contributions require <DCO_OR_CLA>. <SIGN_OFF_INSTRUCTIONS, e.g. Add a
`Signed-off-by` line with `git commit -s`.> Pull requests without it cannot be
merged, and the check will tell you.

## Releases

<!-- GUIDANCE: Contributors need to know when their merged change reaches users.
     Keep this to the shape of the process, not the full runbook. -->

<RELEASE_CADENCE_AND_PROCESS>

Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html); see
the versioning section of the [README](README.md) for what the public API covers.

## Code of conduct

This project follows <CODE_OF_CONDUCT_REFERENCE, e.g. the Contributor Covenant>.
Report unacceptable behaviour to <CONDUCT_CONTACT>.

## Questions

<CONTACT_CHANNEL>.
