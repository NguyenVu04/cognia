"""Locating files that ship with the application.

Nothing outside this module builds a path into ``src/resources/``.
"""

from __future__ import annotations

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
