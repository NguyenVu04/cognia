"""Locating files: the ones that ship, and the ones the user owns.

Nothing outside this module builds a path into ``src/resources/`` or into the
user's data directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_RESOURCES = Path(__file__).resolve().parent.parent / "resources"


def resource(*parts: str) -> Path:
    """Return an absolute path inside ``src/resources/``.

    Raises ``FileNotFoundError`` rather than handing back a path that is not
    there, so a missing font or stylesheet fails at the call site.
    """
    path = _RESOURCES.joinpath(*parts)
    if not path.exists():
        raise FileNotFoundError(f"resource not found: {path}")
    return path


def resource_dir(*parts: str) -> Path:
    """Return an absolute directory inside ``src/resources/``, existing or not."""
    return _RESOURCES.joinpath(*parts)


def data_dir() -> Path:
    """Return the directory Cognia writes to, creating it if need be.

    Everything above is read-only and ships with the application; this is the
    other half — the one place on disk that belongs to the user rather than to
    the build. NFR-04 keeps their data here and nowhere else.

    The standard library only, per the layering rules: no ``platformdirs``.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"

    directory = Path(base) / "Cognia"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def data_file(name: str) -> Path:
    """Return a path inside :func:`data_dir`, existing or not."""
    return data_dir() / name
