"""How a new character version is made from a template or an earlier version.

Pure functions: the time and the new ID are handed in. ``history`` is every
stored version in any order; the one with the highest number is in force.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from src.domain.character.models import CHOSEN, RESTORED, Template, Version


def next_number(history: Sequence[Version]) -> int:
    return max((version.number for version in history), default=0) + 1


def from_template(
    template: Template, history: Sequence[Version], version_id: str, now: datetime
) -> Version:
    """A new version in force, copied from ``template``.

    Raises ``ValueError`` if ``template`` is the one in force: the user changes
    to one of the other characters, not to the same one again.
    """
    current = _in_force(history)
    if current is not None and current.template_id == template.id:
        raise ValueError(f"{template.name} is already the character in force.")
    return Version(
        id=version_id,
        number=next_number(history),
        template_id=template.id,
        name=template.name,
        role=template.role,
        description=template.description,
        appearance_id=template.appearance_id,
        temperament=template.temperament,
        origin=CHOSEN,
        created_at=now,
    )


def restored(
    earlier: Version, history: Sequence[Version], version_id: str, now: datetime
) -> Version:
    """A new version in force, a full copy of ``earlier``.

    The version it replaces stays in ``history``, so the restore can itself be
    undone. Raises ``ValueError`` if ``earlier`` is not in ``history`` or is
    already in force.
    """
    if earlier not in history:
        raise ValueError(f"Version {earlier.number} is not in the history.")
    if earlier == _in_force(history):
        raise ValueError(f"Version {earlier.number} is already in force.")
    return replace(
        earlier,
        id=version_id,
        number=next_number(history),
        origin=RESTORED,
        created_at=now,
    )


def in_force_until(version: Version, history: Sequence[Version]) -> datetime | None:
    """When the next version replaced ``version``, or ``None`` while it is in force."""
    later = [other for other in history if other.number > version.number]
    if not later:
        return None
    return min(later, key=lambda other: other.number).created_at


def _in_force(history: Sequence[Version]) -> Version | None:
    return max(history, key=lambda version: version.number, default=None)
