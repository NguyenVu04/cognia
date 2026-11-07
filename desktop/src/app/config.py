"""Where the model servers and their files live, how they run, how much of the
conversation the model is shown, and where the database file is kept.

Providers are named in configuration rather than loaded as code, so this is the
one place that says "this server, this model". Changing it does not touch the
domain.

There are no secrets here and there is no ``.env``: Cognia has no account and
no credentials of its own. The model servers run on this machine only.

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

#: The two builds of llama-server and the two model files. A relative path is
#: taken from ``desktop/``.
LLAMA_SERVER_VULKAN: str = _DEFAULTS["LLAMA_SERVER_VULKAN"]
LLAMA_SERVER_CPU: str = _DEFAULTS["LLAMA_SERVER_CPU"]
CHAT_MODEL: str = _DEFAULTS["CHAT_MODEL"]
EMBEDDING_MODEL: str = _DEFAULTS["EMBEDDING_MODEL"]

#: These three belong to the embedding model and change with it. Two unrelated
#: lines still reach a cosine of about the baseline; at the near-duplicate
#: cosine a new line counts as one already stored; the model reads 512 tokens,
#: about this many characters of English with a margin.
EMBEDDING_BASELINE: float = _DEFAULTS["EMBEDDING_BASELINE"]
NEAR_DUPLICATE: float = _DEFAULTS["NEAR_DUPLICATE"]
EMBEDDING_MAX_CHARS: int = _DEFAULTS["EMBEDDING_MAX_CHARS"]

#: The chat model's context in tokens. Left to the server, it would reserve the
#: model's full context, which needs far more memory than a conversation uses.
CHAT_CONTEXT: int = _DEFAULTS["CHAT_CONTEXT"]

#: MiB of RAM for the chat server's old prompts; the server's default is too large.
CHAT_CACHE_RAM_MIB: int = _DEFAULTS["CHAT_CACHE_RAM_MIB"]

#: Seconds without a request before a server frees its model; ``null`` keeps it.
MODEL_IDLE_SECONDS: int | None = _DEFAULTS["MODEL_IDLE_SECONDS"]

#: Most tokens one reply may generate, reasoning included; ``null`` means no cap.
REPLY_MAX_TOKENS: int | None = _DEFAULTS["REPLY_MAX_TOKENS"]

#: Most tokens one interpretation may generate, reasoning included.
INTERPRET_MAX_TOKENS: int | None = _DEFAULTS["INTERPRET_MAX_TOKENS"]

#: Most tokens one summary may generate, reasoning included.
SUMMARY_MAX_TOKENS: int | None = _DEFAULTS["SUMMARY_MAX_TOKENS"]

#: How long a server may take to load its model, and how often it may be
#: started again after it ends, in one run.
MODEL_START_SECONDS: float = _DEFAULTS["MODEL_START_SECONDS"]
MODEL_RESTARTS: int = _DEFAULTS["MODEL_RESTARTS"]

#: The characters of history that go to the model. Measured on the chat model:
#: 4 160 of its 8 192 tokens are left for the history once the system text, a
#: summary, the tool schemas, layer 4, tool results and the reply are counted,
#: and short messages cost one token for every 2.6 characters. Past three
#: quarters of this, the older messages are summarized.
HISTORY_MAX_CHARS: int = _DEFAULTS["HISTORY_MAX_CHARS"]

#: The longest message the user can send. About 190 tokens of English, as
#: measured: a long paragraph, read in about 2 seconds on a CPU, and the whole
#: of it fits what the embedding model reads.
MESSAGE_MAX_CHARS: int = _DEFAULTS["MESSAGE_MAX_CHARS"]

#: Where the SQLite file lives. ``null`` means ``cognia.sqlite3`` in the data
#: directory. ``~`` and ``%VARIABLES%`` are expanded, a relative path is taken
#: from ``desktop/``, and an existing folder gets ``cognia.sqlite3`` put inside
#: it. The user's override ``config.json`` always stays in the data directory.
#:
#: Choose a synced folder (OneDrive, Dropbox) and the sync client keeps a second
#: copy of the user's data off the machine, which Cognia promises never
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
    path = _resolve(DATABASE_PATH)
    return path / DATABASE_NAME if path.is_dir() else path


def model_path(value: str) -> Path:
    """One of the model paths above, resolved the same way as the database."""
    return _resolve(value)


def _resolve(value: str) -> Path:
    path = Path(os.path.expandvars(value)).expanduser()
    return path if path.is_absolute() else _APP_DIR / path
