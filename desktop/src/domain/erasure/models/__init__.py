"""The two levels of erasure, the groups of data they remove, and the result."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Level(StrEnum):
    #: Everything remembered, the companion's own memory included. The
    #: character and the settings stay.
    MEMORY = "memory"
    #: Everything, without exception. The settings return to their defaults.
    EVERYTHING = "everything"


class Group(StrEnum):
    """Data that goes together, in an order that no reference blocks."""

    CONVERSATIONS = "conversations"
    MEMORY = "memory"
    DESK = "desk"
    LEARNING = "learning"
    SPEECH = "speech"
    EVENTS = "events"
    CHARACTER = "character"
    SETTINGS = "settings"


@dataclass(frozen=True)
class GroupCount:
    group: Group
    rows: int


@dataclass(frozen=True)
class ErasureReport:
    """What was removed and what was not. ``compacted`` says that the file no
    longer holds the pages of the removed rows."""

    erased: tuple[Group, ...]
    failed: tuple[Group, ...]
    compacted: bool

    @property
    def complete(self) -> bool:
        return not self.failed and self.compacted
