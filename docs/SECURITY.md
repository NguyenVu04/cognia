<!--
  SECURITY POLICY TEMPLATE
  ========================
  Copy to your project root as SECURITY.md. GitHub discovers this file at the
  repository root, in .github/, or in docs/, and surfaces it from the Security
  tab and from the "Report a vulnerability" affordance.

  Same conventions as README.template.md: replace every <PLACEHOLDER>, resolve
  every marker, delete every GUIDANCE comment and this block.

      grep -n '<[A-Z][A-Z0-9_]*>' SECURITY.md      # must return nothing
-->

# Security policy

## Supported versions

<!-- GUIDANCE: Only list what you will actually patch. An overstated support
     window is a commitment you will be held to during an incident. -->

| Version | Supported | Until |
|---|---|---|
| <MAJOR_N>.x | ✅ Security and bug fixes | <DATE_OR_ONGOING> |
| <MAJOR_N_MINUS_1>.x | ⚠️ Security fixes only | <END_OF_SUPPORT_DATE> |
| < <MAJOR_N_MINUS_1>.0 | ❌ Unsupported | — |

## Reporting a vulnerability

**Do not open a public issue, pull request, or discussion for a security problem.**
Public disclosure before a fix is available puts every user at risk.

Report through <REPORTING_CHANNEL, e.g. GitHub private vulnerability reporting at
<REPOSITORY_URL>/security/advisories/new>, or by email to <SECURITY_EMAIL>.

<!-- OPTIONAL: only if you publish a key and will actually decrypt what arrives. -->
For sensitive reports, encrypt to <PGP_KEY_FINGERPRINT> (<PGP_KEY_URL>).

Please include, as far as you can establish it:

- the affected version, component, and configuration;
- reproduction steps or a proof of concept;
- the impact you believe it has;
- any workaround you have found.

## What to expect

| Stage | Target |
|---|---|
| Acknowledgement of your report | <ACKNOWLEDGEMENT_SLA, e.g. 2 business days> |
| Initial assessment and severity | <TRIAGE_SLA, e.g. 5 business days> |
| Fix or mitigation for critical issues | <CRITICAL_FIX_SLA> |
| Fix or mitigation for other issues | <STANDARD_FIX_SLA> |

We will keep you informed at each stage, tell you plainly if we assess the issue
as out of scope or as accepted risk, and credit you in the advisory unless you
ask us not to.

## Scope

**In scope**

- <IN_SCOPE_ASSET_1>
- <IN_SCOPE_ASSET_2>

**Out of scope**

<!-- GUIDANCE: Stating this saves both sides time. The entries below are the
     usual ones; keep what applies and add anything specific to this project. -->

- Findings from automated scanners with no demonstrated exploitability
- Denial of service through sheer volume of traffic
- Social engineering of maintainers or users
- Vulnerabilities in dependencies already covered by a published advisory
- <PROJECT_SPECIFIC_EXCLUSION>

## Disclosure

We follow coordinated disclosure. We aim to publish an advisory within
<DISCLOSURE_WINDOW, e.g. 90 days> of a confirmed report, or sooner once a fix has
shipped. We will agree the timing with you before publishing.

Published advisories: <ADVISORY_URL>.

<!-- REQUIRED-IF: the project runs a paid bug bounty or a formal safe-harbour
     programme. Delete otherwise — do not imply a bounty you do not fund. -->
## Safe harbour

We will not pursue legal action for good-faith security research conducted under
this policy: staying within scope, avoiding privacy violations and service
degradation, and giving us reasonable time to respond before disclosure.

Bounty details: <BOUNTY_PROGRAMME_URL>.
