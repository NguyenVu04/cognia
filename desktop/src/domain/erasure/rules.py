"""Which groups each level of erasure removes."""

from __future__ import annotations

from src.domain.erasure.models import Group, Level

_MEMORY = (
    Group.CONVERSATIONS,
    Group.MEMORY,
    Group.DESK,
    Group.LEARNING,
    Group.JOURNAL,
    Group.SPEECH,
    Group.EVENTS,
)


def groups(level: Level) -> tuple[Group, ...]:
    """The groups in the order they are removed. The character goes after
    everything that refers to it, and the settings last."""
    if level is Level.MEMORY:
        return _MEMORY
    return (*_MEMORY, Group.CHARACTER, Group.SETTINGS)
