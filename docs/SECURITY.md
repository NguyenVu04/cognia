# Security policy

Cognia is maintained by one person, Nguyễn Duy Vũ, alongside academic work. This
document says what is supported, how to report a problem, and what you can realistically
expect back — written to be accurate rather than reassuring.

## Supported versions

No version has been released. There is no application to patch yet; this repository
currently holds the use case specification, the architecture decision records, and the
project documents.

| Version | Supported | Until |
|---|---|---|
| `main` (unreleased) | ✅ Fixes go here | Ongoing |
| Any release | — | None exists yet |

When there is a first release, this table will name the version lines that get
security fixes and for how long. Nothing is promised in advance of that.

## Reporting a vulnerability

**Do not open a public issue, pull request, or discussion for a security problem.**
Public disclosure before a fix is available puts every user at risk.

Report by email to nguyenvu04.work@gmail.com, or through GitHub private vulnerability
reporting at https://github.com/NguyenVu04/cognia/security/advisories/new.

Please include, as far as you can establish it:

- the affected version, component, and configuration;
- reproduction steps or a proof of concept;
- the impact you believe it has;
- any workaround you have found.

## What to expect

There is one maintainer, so these are honest expectations rather than a service level
anyone is held to.

| Stage | Target |
|---|---|
| Acknowledgement of your report | Within 5 days |
| Initial assessment and severity | Within 14 days |
| Fix or mitigation | Once there is a release to fix. Until then, a confirmed report changes the specification or an ADR instead, and the change says what it came from |

You will be kept informed at each stage, told plainly if the issue is assessed as out
of scope or as an accepted risk, and credited in the advisory unless you ask otherwise.

## Scope

**In scope**

- The Cognia desktop application, once released — and above all anything that breaks
  one of the guarantees the product is built on:
  - data leaving the machine that the user did not switch on (NFR-01);
  - reading anything from the operating system beyond idle time, lock state,
    presentation state and screen layout — keystrokes, screenshots, the clipboard,
    browsing history, or which window is open (NFR-03, C-05);
  - a proactive message reaching the user without a complete explanation attached,
    which means something bypassed the `SpeechGate` (NFR-10, ADR 0001);
  - data surviving an erasure the user asked for (UC-14, NFR-04);
  - a character description switching off the safety behaviour it must never be able
    to switch off (FR-04, NFR-13).
- The contents of this repository — anything here that would execute on a reader's
  machine, or that would mislead a reader into an unsafe action.

**Out of scope**

- Findings from automated scanners with no demonstrated exploitability.
- Denial of service through sheer volume of traffic. There is no server to flood:
  Cognia has no account, no backend, and no network listener (C-02, NFR-01).
- Social engineering of the maintainer or of users.
- Vulnerabilities in dependencies already covered by a published advisory.
- Anything that requires a second account on the machine, or physical access to it
  while unlocked. Cognia is specified as one user on one machine (C-02), and the data
  on disk is protected by the operating system's account boundary and nothing further
  — this is a stated accepted risk, not an oversight.
- The AI model or outside AI service the user chose to run. Cognia warns before the
  first send and records every send afterwards (NFR-02); what that service does with
  what it receives is between the user and that service.

## Disclosure

Coordinated disclosure. The aim is to publish an advisory within 90 days of a confirmed
report, or sooner once a fix has shipped, and the timing will be agreed with you before
publishing.

Published advisories: https://github.com/NguyenVu04/cognia/security/advisories
