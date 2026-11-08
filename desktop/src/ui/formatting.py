"""Dates and durations as the interface writes them. The interface is in
English only, whatever the system locale."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QLocale

_ENGLISH = QLocale(QLocale.Language.English)


def short_date(day: date) -> str:
    """For example "5 Nov"."""
    return _ENGLISH.toString(day, "d MMM")


def long_date(day: date) -> str:
    """For example "5 November"."""
    return _ENGLISH.toString(day, "d MMMM")


def local_day(moment: datetime) -> date:
    return moment.astimezone().date()


def duration(minutes: int) -> str:
    """For example "45 minutes", "1 hour", "2 hours 5 minutes"."""
    minutes = max(0, minutes)
    hours, rest = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if rest or not hours:
        parts.append(f"{rest} minute{'s' if rest != 1 else ''}")
    return " ".join(parts)
