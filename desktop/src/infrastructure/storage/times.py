"""The one stored form of an instant, shared by every store.

Times are stored in UTC. A naive ``datetime`` handed in is read as local time.
"""

from __future__ import annotations

from datetime import datetime, timezone


def to_utc(moment: datetime) -> datetime:
    """The same instant in UTC; a naive value is taken to be local time."""
    return moment.astimezone(timezone.utc)


def to_text(moment: datetime) -> str:
    """The stored form: fixed width, so text order is time order."""
    return to_utc(moment).isoformat(timespec="milliseconds")
