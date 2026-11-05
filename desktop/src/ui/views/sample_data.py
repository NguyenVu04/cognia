"""Placeholder copy for the mockup screens.

**This is mockup text, not domain data.** Every string here exists so the
screens can be drawn with something in them. None
of it is read from disk, none of it is a model, and nothing in the
specification depends on it. When the domain arrives this module is deleted
whole and the views are fed from ``src/domain/`` instead.

Nothing else under ``src/ui/`` may hard-code screen copy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    id: str
    label: str
    icon: str


@dataclass(frozen=True)
class Message:
    role: str  # "c" companion, "u" user
    text: str
    note: str = ""


@dataclass(frozen=True)
class PastSession:
    intent: str
    answer: str
    when: str
    length: str


@dataclass(frozen=True)
class Level:
    id: str
    name: str
    detail: str


@dataclass(frozen=True)
class MessageKind:
    id: str
    name: str
    detail: str


@dataclass(frozen=True)
class PauseOption:
    id: str
    label: str
    icon: str
    paused_label: str


NAV: list[NavItem] = [
    NavItem("chat", "Companion", "chat-circle"),
    NavItem("sessions", "Sessions", "timer"),
    NavItem("memory", "Memory", "brain"),
    NavItem("character", "Character", "user-focus"),
    NavItem("desk", "Desk awareness", "eye"),
    NavItem("proactivity", "Speaking up", "bell-simple"),
]

MESSAGES: list[Message] = [
    Message("c", "Morning. Yesterday ended mid-way through the positioning "
                 "chapter — you said the second half needed rewriting."),
    Message("c", "Nothing else is outstanding."),
    Message("u", "right. going to try and finish it today"),
    Message("c", "Noted. I have written that down as it stands: “Wants to "
                 "finish the positioning chapter today.” Correct it if that "
                 "is not it.",
            "Stored — you told me · 15 Aug"),
]

SESSION_INTENT = "Positioning chapter, second pass"
SESSION_OPENED = "Open since 09:15"
SESSION_ELAPSED = "2h 47m"

PAST_SESSIONS: list[PastSession] = [
    PastSession("Positioning chapter, first pass",
                "“Got the shape of it, not the words.”", "14 Aug", "3h 10m"),
    PastSession("Reading — competitor teardown",
                "No answer given", "13 Aug", "1h 25m"),
    PastSession("Use case spec, section 5",
                "“Cut four things. Good day.”", "12 Aug", "2h 02m"),
]

READS: list[str] = [
    "How long since the mouse or keyboard was touched",
    "Whether the machine is locked",
    "Whether you are presenting full-screen",
]

NEVER_READS: list[str] = [
    "What you type",
    "The screen",
    "The clipboard",
    "Browsing history",
    "Which application or window is open — including where it sits",
]

LEVELS: list[Level] = [
    Level("quiet", "Quiet", "1 a day"),
    Level("moderate", "Moderate", "3 a day"),
    Level("present", "Present", "6 a day"),
]

KINDS: list[MessageKind] = [
    MessageKind("break", "Break nudge", "The only thing sent during a session"),
    MessageKind("return", "Coming back to the desk",
                "What you were in the middle of"),
    MessageKind("greeting", "Greeting when you open Cognia",
                "Does not count against the allowance"),
    MessageKind("propose", "Asking to change how it behaves",
                "Only ever asks; never just does it"),
]

QUIET_HOURS = "22:00 → 07:00"

PAUSE_OPTIONS: list[PauseOption] = [
    PauseOption("hour", "For one hour", "clock", "for an hour"),
    PauseOption("today", "Until the end of today", "moon", "until the end of today"),
    PauseOption("off", "Until I switch it back on", "power",
                "until you switch it back on"),
]

NUDGE_TEXT = (
    "You have been at the machine for 2 hours 47 minutes. Worth standing up "
    "for a few?"
)

NUDGE_WHY: list[str] = [
    "At the machine continuously since 09:15 — 2h 47m",
    "Your break threshold — 90 minutes",
    "Held 12 minutes because you were typing",
    "Allowance used — 1 of 3 today",
]
