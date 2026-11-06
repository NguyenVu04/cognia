# 9. Tools at run time through MCP servers

- **Status:** Proposed
- **Date:** 2026-11-06
- **Deciders:** Nguyễn Duy Vũ
- **Supersedes:** ADR 0001 in part: its statement that extensibility is an explicit anti-goal, and that
  reason for the rejection of a microkernel. The rest of ADR 0001 stays in force
- **Superseded by:** —

## Context

ADR 0001 made extensibility an explicit anti-goal. It gave two reasons. A plug-in contract costs work
that the project never gets back. A plug-in that loads code into the process makes FR-04 and NFR-12
unenforceable, because such code can replace the safety rules.

Specification version 6.0 gives the companion tools in a reply (UC-27, FR-40), and lets the user add
tool servers of their own (FR-41). The author wants the companion to be easier to extend. The Model
Context Protocol (MCP) is a published protocol for tool servers. A server runs as its own process, and
a client calls its tools over standard input and output, or over HTTP.

NFR-01 and G-05 promised zero outbound connections. A tool server that the user adds can connect to
anything.

## Decision

**The user can add MCP tool servers.** None is present after installation. The settings list each
server, and the user can remove it.

**A server runs outside the Cognia process.** Cognia starts it, or connects to it, through the MCP
client in `infrastructure/ai`. No code loads a module from outside the install folder (rule 13 of
section 6.2 of [`ARCHITECTURE.md`](../ARCHITECTURE.md)). So no server can change the base rules, the
SpeechGate, the safety check or the limits on Win32 calls.

**The user agrees before the first use.** Before Cognia calls a server for the first time, it states
that the server can send what it receives off the machine, and it waits for the user to agree.

**Tools stay inside a reply.** A server tool runs only in a reply that the user asked for, through the
same tool loop as the tools that ship (D-58). The reply still passes `reply_complies` (NFR-12).

**NFR-01 measures Cognia.** The network capture of QA-01 covers Cognia and its child processes, with no
server added. A server that the user adds is outside that measure.

## Consequences

**Positive:**

- New tools need no new release of Cognia.
- The safety rules stay inside the process, so FR-04 and NFR-12 still hold by construction.

**Negative:**

- Data that the user sends to a server can leave the machine. C-03, NFR-01 and G-05 now have an
  exception that the user chooses.
- More tools make wrong tool calls more likely for a small model (section 12 of `ARCHITECTURE.md`).
- A server can be slow or fail. The reply then says that the tool failed (UC-27-E1).

**Neutral:**

- The other decisions of ADR 0001 do not change: the layers, the ports, one ordered queue with one
  reader, one SpeechGate, a pure domain and an append-only log.

## Alternatives considered

**Python plug-ins inside the process.** Simple to load. Rejected, because a plug-in can replace any
function, the safety rules and the Win32 limits included. This is the reason that ADR 0001 gave, and
it still holds.

**Only the developer adds tools.** NFR-01 stays as it was. Rejected, because the author wants
extension at run time.

**Keep the anti-goal.** No change. Rejected for the same reason.
