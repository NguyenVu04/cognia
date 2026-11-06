"""Domain models. The standard library only — no Qt, no adapters, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.events.models import EventKind, Payload


@dataclass(frozen=True)
class PresenceChange:
    """A change the sampler saw, to be recorded as an event at ``at``."""

    kind: EventKind
    payload: Payload
    at: datetime


@dataclass(frozen=True)
class DeskTime:
    """Minutes at the machine since the day began, and since the last break.
    ``since_break_minutes`` is ``None`` while the user is away."""

    today_minutes: int
    since_break_minutes: int | None
    at_desk: bool


__all__ = ["DeskTime", "PresenceChange"]
