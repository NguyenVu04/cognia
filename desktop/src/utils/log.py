"""The error log: one file in the data folder, and one older file.

It keeps what the application did and what went wrong, with the message of each
error. A message can hold the user's words, so the log is personal data: it
never leaves the machine, and erasing memory erases it.

Modules write to it through ``logging.getLogger(__name__)``. Only loggers under
``src`` reach the file, so a library's own lines stay out.
"""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

FILE_NAME = "cognia.log"
# The file starts again at this size, and one older file is kept.
MAX_BYTES = 1024 * 1024
_FORMAT = "%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"

_application = logging.getLogger("src")
_handler: RotatingFileHandler | None = None
_hooks: tuple | None = None


def start(path: Path) -> None:
    """Write the log to ``path`` from now on, and log every error that nobody
    handled, on any thread. Raises ``OSError`` if the file cannot be opened."""
    global _handler, _hooks
    stop()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    _application.addHandler(handler)
    _application.setLevel(logging.INFO)
    _handler = handler
    _hooks = (sys.excepthook, threading.excepthook)
    sys.excepthook = _unhandled
    threading.excepthook = _unhandled_in_thread


def stop() -> None:
    """Close the file and put the earlier error hooks back."""
    global _handler, _hooks
    if _handler is not None:
        _application.removeHandler(_handler)
        _handler.close()
        _handler = None
    if _hooks is not None:
        sys.excepthook, threading.excepthook = _hooks
        _hooks = None


def entries() -> int:
    """The lines in both files, or 0 before :func:`start`. Raises ``OSError``
    if a file cannot be read."""
    total = 0
    for path in _files():
        try:
            with path.open("rb") as file:
                total += sum(1 for _ in file)
        except FileNotFoundError:
            continue
    return total


def erase() -> None:
    """Remove both files. Logging goes on in a new file. Raises ``OSError`` if
    a file cannot be removed."""
    handler = _handler
    if handler is None:
        return
    with handler.lock:
        if handler.stream is not None:
            handler.stream.close()
            # The next line opens the file again.
            handler.stream = None
        for path in _files():
            path.unlink(missing_ok=True)


def _files() -> list[Path]:
    if _handler is None:
        return []
    current = Path(_handler.baseFilename)
    return [current, current.with_name(f"{current.name}.1")]


def _unhandled(kind, error, trace) -> None:
    _application.error("Unhandled error", exc_info=(kind, error, trace))
    sys.__excepthook__(kind, error, trace)


def _unhandled_in_thread(args) -> None:
    _application.error(
        "Unhandled error in thread %s",
        args.thread.name if args.thread else "?",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
