"""The port through which the four facts about the user are read.

The data type is the limit: it has a field for each fact that may be read, and
no field for anything else, so no code above the adapter can ask for a window
title, a position, a keystroke or the screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PresenceSample:
    """The four facts, at one moment. ``foreground_app`` is the file name of the
    program in front, such as ``code.exe``, or "" if none can be named."""

    idle_seconds: int
    locked: bool
    presenting: bool
    foreground_app: str


class PresenceFailed(Exception):
    """The facts cannot be read on this machine, with a sentence saying so."""


class PresenceSource(Protocol):
    """Reads the four facts."""

    def sample(self) -> PresenceSample:
        """The facts now. Raises :class:`PresenceFailed` if the time since the
        last input cannot be read, because then nothing else can be trusted."""
        ...
