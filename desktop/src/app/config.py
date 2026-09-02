"""Where the model lives and how much of the conversation it is shown.

ADR 0001 keeps providers named in configuration rather than loaded as code, so
this is the one place that says "Ollama, on this port, this model". Changing it
does not touch the domain.

There are no secrets here and there is no ``.env``: Cognia has no account and
no credentials of its own (NFR-01, C-02). The only endpoint is a daemon on the
user's own machine. ``config.json`` in the data directory overrides the
defaults if the user writes one; it is not created for them.
"""

from __future__ import annotations

import json

from src.utils import paths

OLLAMA_MODEL = "qwen3.5:2b"
OLLAMA_BASE_URL = "http://localhost:11434"

#: How many past messages go to the model. The window is deliberately smaller
#: than the model's context: a long history costs first-token latency, and
#: NFR-06 asks for words within three seconds.
HISTORY_MESSAGES = 40

_OVERRIDABLE = ("OLLAMA_MODEL", "OLLAMA_BASE_URL", "HISTORY_MESSAGES")


def load() -> None:
    """Apply ``config.json`` from the data directory, if there is one.

    A malformed or unreadable file is ignored rather than fatal — a typo in an
    optional settings file should not stop the application starting.
    """
    path = paths.data_file("config.json")
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(settings, dict):
        return
    for key in _OVERRIDABLE:
        if key in settings:
            globals()[key] = settings[key]


def system_prompt(name: str, role: str) -> str:
    """The character, said to the model in the second person.

    Temporary: the character is mockup copy until ``core/`` owns it (FR-02).
    """
    return (
        f"You are {name}, {role}. You are a companion on someone's desktop, not "
        "an assistant. You do not manage tasks, set reminders, or act on the "
        "user's behalf.\n"
        "Talk the way a friend does: warm, brief, curious. One or two short "
        "paragraphs at most, usually less. Ask about them more than you talk "
        "about yourself.\n"
        "Never invent things they have told you. If you do not remember "
        "something, say so.\n"
        "If they raise something serious about their mental health, say plainly "
        "that you are a program and cannot help with it, and do not pretend "
        "otherwise for the sake of staying in character."
    )
