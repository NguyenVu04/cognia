"""Where the model lives, how much of the conversation it is shown, and where
the database file is kept.

ADR 0001 keeps providers named in configuration rather than loaded as code, so
this is the one place that says "Ollama, on this port, this model". Changing it
does not touch the domain.

There are no secrets here and there is no ``.env``: Cognia has no account and
no credentials of its own (NFR-01, C-02). The only endpoint is a daemon on the
user's own machine.

The defaults ship in ``src/config.json``. A ``config.json`` in the data
directory overrides any of the same keys if the user writes one; it is not
created for them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.utils import paths

# Shipped with the application, so a missing or broken file is a build fault
# and fails loudly here, unlike the user's optional override below.
_APP_DIR = Path(__file__).resolve().parents[2]  # desktop/

_DEFAULTS = json.loads((_APP_DIR / "src" / "config.json").read_text(encoding="utf-8"))

OLLAMA_MODEL: str = _DEFAULTS["OLLAMA_MODEL"]
OLLAMA_BASE_URL: str = _DEFAULTS["OLLAMA_BASE_URL"]

#: How many past messages go to the model. The window is deliberately smaller
#: than the model's context: a long history costs first-token latency, and
#: NFR-06 asks for words within three seconds.
HISTORY_MESSAGES: int = _DEFAULTS["HISTORY_MESSAGES"]

#: Where the SQLite file lives. ``null`` means ``cognia.sqlite3`` in the data
#: directory. ``~`` and ``%VARIABLES%`` are expanded, a relative path is taken
#: from ``desktop/``, and an existing folder gets ``cognia.sqlite3`` put inside
#: it. The user's override ``config.json`` always stays in the data directory.
#:
#: Choose a synced folder (OneDrive, Dropbox) and the sync client keeps a second
#: copy of the user's data off the machine, which NFR-04 and C-02 promise never
#: happens. That is the user's call to make, not a default.
DATABASE_PATH: str | None = _DEFAULTS["DATABASE_PATH"]

DATABASE_NAME = "cognia.sqlite3"

# Every shipped key, and only those, may be overridden.
_OVERRIDABLE = tuple(_DEFAULTS)


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


def database_path() -> Path:
    """The database file, from ``DATABASE_PATH`` or the default location."""
    if not DATABASE_PATH:
        return paths.data_file(DATABASE_NAME)
    path = Path(os.path.expandvars(DATABASE_PATH)).expanduser()
    if not path.is_absolute():
        path = _APP_DIR / path
    return path / DATABASE_NAME if path.is_dir() else path


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
