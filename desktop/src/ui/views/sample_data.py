"""Placeholder copy from the design document.

**This is mockup text, not domain data.** Every string here was written into
the Cognia design so the screens could be drawn with something in them. None
of it is read from disk, none of it is a model, and nothing in the
specification depends on it. When the domain arrives this module is deleted
whole and the views are fed from ``src/core/`` instead.

Nothing else under ``src/ui/`` may hard-code screen copy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    role: str
    sample: str


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
class MemoryItem:
    id: str
    text: str
    date: str
    evidence: str = ""


@dataclass(frozen=True)
class CharacterVersion:
    summary: str
    date: str


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


CHARACTERS: list[Character] = [
    Character("wren", "Wren", "Archivist",
              "You said the second half needed rewriting. Still true?"),
    Character("otto", "Otto", "Old colleague",
              "Two hours on the one chapter. That is where you stopped."),
    Character("mira", "Mira", "Studio neighbour",
              "I am here. Say when you start and I will leave you to it."),
    Character("kes", "Kes", "Night reader",
              "It is late. I will not keep you."),
]

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

TOLD: list[MemoryItem] = [
    MemoryItem("t1", "Works best in the morning; afternoons are for reading.", "2 Aug"),
    MemoryItem("t2", "Prefers short answers. Asked for it, said to keep it.", "7 Aug"),
    MemoryItem("t3", "Thesis is due 15 December.", "11 Aug"),
]

NOTICED: list[MemoryItem] = [
    MemoryItem("n1", "Sessions rarely run past 16:00.", "14 Aug",
               "18 of 21 recorded sessions ended before 16:00, 2–14 Aug."),
    MemoryItem("n2", "Break nudges are usually postponed once, then taken.", "13 Aug",
               "5 of 6 nudges postponed by 20 minutes, then followed by 12+ "
               "minutes away."),
]

CHARACTER_TEXT = (
    "Wren, an archivist who has read too much and says too little. Short "
    "sentences. Never flatters, never congratulates. Asks one thing at a time "
    "and lets a silence sit. Says plainly when it does not know."
)

CHARACTER_VERSIONS: list[CharacterVersion] = [
    CharacterVersion("Added: never congratulates", "9 Aug"),
    CharacterVersion("Shorter sentences; dropped the greeting line", "4 Aug"),
    CharacterVersion("First written character", "12 Mar"),
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

TOGETHER_SINCE = "together since 12 March"
