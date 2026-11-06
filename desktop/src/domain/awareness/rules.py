"""Whether the user is at the machine, and for how long, from the recorded events.

Pure functions. Every time arrives on an event or as an argument, so the same
log always gives the same answer. Time nobody observed is never counted: a run
at the desk ends when the user went idle, when the clock jumped, when desk
awareness was switched off, or at the last event before a restart.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, time, timedelta

from src.domain.awareness.models import DeskTime
from src.domain.events.models import Event, EventKind, Payload
from src.domain.ports.presence_source import PresenceSample

# Start values; trial use sets the final ones.
AWAY_AFTER = 300
BREAK_RESET = 300
# A day at the machine begins at this local time, so a late night counts with
# the evening before it.
DAY_START = time(4)
# The wall clock moved this much further than the sampler waited: the machine
# slept, or the clock was changed.
GAP_SECONDS = 60
AWARENESS_ON = "awareness_on"

AWARENESS_OFF_TIME = "Desk awareness is off, so time at the machine is not known."
AWARENESS_OFF_APPS = "Desk awareness is off, so the applications are not known."
NOT_SEEN = "The user has not been seen at the machine today."
NO_APPS = "No application time is recorded today."

_Change = tuple[EventKind, Payload]


def at_desk(sample: PresenceSample) -> bool:
    """Input in the last ``AWAY_AFTER`` seconds, and the machine not locked."""
    return sample.idle_seconds < AWAY_AFTER and not sample.locked


def presence_events(
    previous: PresenceSample | None, current: PresenceSample
) -> tuple[_Change, ...]:
    """The events for ``current``: only what changed since ``previous``. With
    no previous sample, after a start or a jump of the clock, everything is
    reported, marked ``first``."""
    first = previous is None
    changes: list[_Change] = []
    now = (at_desk(current), current.locked, current.presenting)
    if first or now != (at_desk(previous), previous.locked, previous.presenting):
        changes.append(
            (
                EventKind.PRESENCE,
                {
                    "at_desk": now[0],
                    "locked": current.locked,
                    "presenting": current.presenting,
                    "idle_seconds": current.idle_seconds,
                    "first": first,
                },
            )
        )
    if first or current.foreground_app != previous.foreground_app:
        changes.append((EventKind.FOREGROUND_APP, {"app": current.foreground_app}))
    return tuple(changes)


def stopped_event() -> _Change:
    """The event when reading stops, by a pause or by switching off: from then
    on nothing is observed, so nothing is counted."""
    return (
        EventKind.PRESENCE,
        {"at_desk": False, "locked": False, "presenting": False,
         "idle_seconds": 0, "first": False, "stopped": True},
    )


def day_start(moment: datetime) -> datetime:
    """The start of the day that ``moment`` belongs to, in its own time zone."""
    start = moment.replace(
        hour=DAY_START.hour, minute=0, second=0, microsecond=0
    )
    return start if moment >= start else start - timedelta(days=1)


def desk_time(events: Iterable[Event], now: datetime) -> DeskTime:
    """Minutes at the machine since the day of ``now`` began, and since the
    last break of ``BREAK_RESET`` seconds or more."""
    stretches = _stretches(events, now)
    begin = day_start(now)
    seconds = sum(
        max(0.0, (min(end, now) - max(start, begin)).total_seconds())
        for start, end in stretches
    )
    here = bool(stretches) and stretches[-1][1] == now
    since_break = None
    if here:
        run_start = stretches[-1][0]
        for start, end in reversed(stretches[:-1]):
            if (run_start - end).total_seconds() >= BREAK_RESET:
                break
            run_start = start
        since_break = int((now - run_start).total_seconds() // 60)
    return DeskTime(int(seconds // 60), since_break, here)


def app_minutes(
    events: Iterable[Event], start: datetime, end: datetime
) -> dict[str, int]:
    """Minutes in each application between ``start`` and ``end``, counted only
    while the user was at the machine."""
    totals: dict[str, float] = {}
    app, here, since = "", False, None
    # Every event is read, in log order: a clock set back can put a later seq at
    # an earlier time, and each interval is cut to the window anyway.
    for event in events:
        observed = not (event.kind == EventKind.PRESENCE and event.payload.get("first"))
        if here and app and since is not None and observed:
            _add(totals, app, since, event.occurred_at, start, end)
        if event.kind == EventKind.PRESENCE:
            here = bool(event.payload.get("at_desk"))
        elif event.kind == EventKind.FOREGROUND_APP:
            app = str(event.payload.get("app", ""))
        elif event.kind == EventKind.CLOCK_GAP or _switched_off(event):
            here = False
        since = event.occurred_at
    if here and app and since is not None:
        _add(totals, app, since, end, start, end)
    return {name: int(seconds // 60) for name, seconds in totals.items()}


def desk_time_text(desk: DeskTime | None) -> str:
    """What ``desk_time`` tells the model. ``None`` means awareness is off."""
    if desk is None:
        return AWARENESS_OFF_TIME
    if desk.today_minutes == 0 and not desk.at_desk:
        return NOT_SEEN
    text = f"At the machine today: {_duration(desk.today_minutes)}."
    if desk.since_break_minutes is not None:
        text += f" Since the last break: {_duration(desk.since_break_minutes)}."
    return text


def app_usage_text(minutes: Mapping[str, int] | None) -> str:
    """What ``app_usage`` tells the model. ``None`` means awareness is off."""
    if minutes is None:
        return AWARENESS_OFF_APPS
    shown = sorted(
        ((app, m) for app, m in minutes.items() if m > 0),
        key=lambda pair: (-pair[1], pair[0]),
    )
    if not shown:
        return NO_APPS
    return "Today: " + "; ".join(f"{a} {_duration(m)}" for a, m in shown) + "."


def _stretches(events: Iterable[Event], now: datetime) -> list[tuple]:
    """Each run of observed presence at the desk, as (start, end)."""
    stretches: list[tuple] = []
    start = None
    last_seen = None

    def close(end: datetime) -> None:
        nonlocal start
        stretches.append((start, max(start, end)))
        start = None

    for event in events:
        if event.kind == EventKind.PRESENCE:
            if event.payload.get("first") and start is not None:
                close(last_seen)
            if event.payload.get("at_desk"):
                if start is None:
                    start = event.occurred_at
            elif start is not None:
                # The user left when the input stopped, not when it was noticed.
                idle = int(event.payload.get("idle_seconds", 0))
                close(event.occurred_at - timedelta(seconds=idle))
        elif event.kind == EventKind.CLOCK_GAP:
            if start is not None:
                gap = int(event.payload.get("seconds", 0))
                close(event.occurred_at - timedelta(seconds=gap))
        elif _switched_off(event):
            if start is not None:
                close(event.occurred_at)
        elif event.kind != EventKind.FOREGROUND_APP:
            continue
        last_seen = event.occurred_at
    if start is not None:
        stretches.append((start, now))
    return stretches


def _switched_off(event: Event) -> bool:
    return (
        event.kind == EventKind.SETTING_CHANGED
        and event.payload.get("name") == AWARENESS_ON
        and not event.payload.get("value")
    )


def _add(
    totals: dict[str, float],
    app: str,
    since: datetime,
    until: datetime,
    start: datetime,
    end: datetime,
) -> None:
    seconds = (min(until, end) - max(since, start)).total_seconds()
    if seconds > 0:
        totals[app] = totals.get(app, 0.0) + seconds


def _duration(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest} min" if hours else f"{rest} min"
