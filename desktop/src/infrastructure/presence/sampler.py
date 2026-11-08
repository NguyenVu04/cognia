"""The thread that reads the four facts once a second and reports changes only.

It reports a change of desk, lock or presentation state, a change of the
application in front, the end of each hour, and a jump of the clock. Between
changes it reports nothing, so a day at the desk is a handful of events. When
asked, it also reports the next pause in typing, once.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime

from src.domain.awareness import rules
from src.domain.awareness.models import PresenceChange
from src.domain.events.models import EventKind
from src.domain.ports import PresenceFailed, PresenceSample, PresenceSource

INTERVAL_SECONDS = 1.0
# Idle this long counts as a pause in typing.
TYPING_PAUSE_SECONDS = 3


def _now() -> datetime:
    return datetime.now().astimezone()


class PresenceSampler(threading.Thread):
    """Reads ``source`` until ``stop`` is set. ``report`` receives each
    :class:`PresenceChange`; ``failed`` receives a sentence once, when the facts
    cannot be read, and the thread ends. The stop flag is read before each
    sample, so reading stops within one interval."""

    def __init__(
        self,
        source: PresenceSource,
        report: Callable[[PresenceChange], None],
        failed: Callable[[str], None],
        stop: threading.Event,
        *,
        clock: Callable[[], datetime] = _now,
        interval: float = INTERVAL_SECONDS,
    ) -> None:
        super().__init__(name="cognia-presence", daemon=True)
        self._source = source
        self._report = report
        self._failed = failed
        self._stop_flag = stop
        self._clock = clock
        self._interval = interval
        self._watch = threading.Event()

    def watch_for_pause(self) -> None:
        """Report the next pause in typing once, as a ``typing_pause`` event.
        Safe from any thread."""
        self._watch.set()

    def run(self) -> None:
        previous: PresenceSample | None = None
        last: datetime | None = None
        while not self._stop_flag.is_set():
            try:
                sample = self._source.sample()
            except PresenceFailed as error:
                self._failed(str(error))
                return
            if self._stop_flag.is_set():
                break
            now = self._clock()
            if last is not None:
                if _hour(now) != _hour(last):
                    self._send(EventKind.APP_HOUR_CLOSED,
                               {"hour_start": _hour(last).isoformat()}, now)
                jump = abs((now - last).total_seconds()) - self._interval
                if jump > rules.GAP_SECONDS:
                    self._send(EventKind.CLOCK_GAP, {"seconds": int(jump)}, now)
                    previous = None  # what follows is reported afresh
            for kind, payload in rules.presence_events(previous, sample):
                self._send(kind, payload, now)
            if self._watch.is_set() and sample.idle_seconds >= TYPING_PAUSE_SECONDS:
                self._watch.clear()
                self._send(EventKind.TYPING_PAUSE,
                           {"idle_seconds": sample.idle_seconds}, now)
            previous, last = sample, now
            self._stop_flag.wait(self._interval)
        if previous is not None:
            kind, payload = rules.stopped_event()
            self._send(kind, payload, self._clock())

    def _send(self, kind: EventKind, payload, at: datetime) -> None:
        self._report(PresenceChange(kind, payload, at))


def _hour(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)
