import ast
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.domain.events.models import EventKind
from src.domain.ports import PresenceFailed, PresenceSample
from src.infrastructure.presence import win32_source
from src.infrastructure.presence.sampler import PresenceSampler

ALLOWED = {
    "GetLastInputInfo", "GetTickCount64", "WTSQuerySessionInformationW",
    "WTSFreeMemory", "SHQueryUserNotificationState", "GetForegroundWindow",
    "GetWindowThreadProcessId", "OpenProcess", "QueryFullProcessImageNameW",
    "CloseHandle",
}
FORBIDDEN = (
    "GetWindowText", "GetWindowRect", "GetWindowInfo", "EnumWindows",
    "SetWindowsHookEx", "GetAsyncKeyState", "GetKeyState", "GetClipboardData",
    "BitBlt", "GetCursorPos",
)
_DLLS = {"_user32", "_kernel32", "_wtsapi32", "_shell32"}
_LOCALS = {"u", "k", "w", "s"}


def _called_functions() -> set[str]:
    tree = ast.parse(Path(win32_source.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        owner = node.value
        if isinstance(owner, ast.Attribute) and owner.attr in _DLLS:
            names.add(node.attr)
        elif isinstance(owner, ast.Name) and owner.id in _LOCALS:
            names.add(node.attr)
    return names


def test_win32_uses_only_allowed_functions() -> None:
    assert _called_functions() == ALLOWED


def test_win32_names_no_forbidden_function() -> None:
    source = Path(win32_source.__file__).read_text(encoding="utf-8")

    assert [name for name in FORBIDDEN if name in source] == []


@pytest.mark.skipif(sys.platform != "win32", reason="reads Windows itself")
def test_win32_smoke() -> None:
    taken = win32_source.Win32PresenceSource().sample()

    assert taken.idle_seconds >= 0
    assert "\\" not in taken.foreground_app and "/" not in taken.foreground_app


# ── the sampler ──────────────────────────────────────────────────────────


class FakeSource:
    def __init__(self, samples, stop: threading.Event, failure: str | None = None):
        self.samples = list(samples)
        self.stop = stop
        self.failure = failure
        self.taken = 0

    def sample(self) -> PresenceSample:
        """Each sample in turn; then the stop flag, as a pause sets it while a
        sample is being taken, so the sampler drops that one."""
        if self.failure:
            raise PresenceFailed(self.failure)
        self.taken += 1
        if len(self.samples) == 1:
            self.stop.set()
            return self.samples[0]
        return self.samples.pop(0)


class Clock:
    def __init__(self, times) -> None:
        self.times = list(times)

    def __call__(self) -> datetime:
        return self.times.pop(0) if len(self.times) > 1 else self.times[0]


START = datetime(2026, 11, 6, 9, 59, 58, tzinfo=timezone.utc)


def run(samples, times, failure=None):
    stop = threading.Event()
    reported, failed = [], []
    sampler = PresenceSampler(
        FakeSource(samples, stop, failure), reported.append, failed.append, stop,
        clock=Clock(times), interval=0,
    )
    sampler.run()
    return reported, failed


def here(app="code.exe", idle=0) -> PresenceSample:
    return PresenceSample(idle, False, False, app)


def test_sampler_reports_changes_only() -> None:
    middle = START + timedelta(minutes=30)
    times = [middle + timedelta(seconds=n) for n in range(5)]
    samples = [here(), here(idle=1), here(app="firefox.exe"), here(app="firefox.exe")]

    reported, _ = run([*samples, samples[-1]], times)

    kinds = [c.kind for c in reported]
    assert kinds == [EventKind.PRESENCE, EventKind.FOREGROUND_APP,
                     EventKind.FOREGROUND_APP, EventKind.PRESENCE]
    assert reported[-1].payload["stopped"] is True


def test_sampler_stops_within_one_sample() -> None:
    stop = threading.Event()
    source = FakeSource([here()] * 5, threading.Event())
    stop.set()
    sampler = PresenceSampler(source, lambda c: None, lambda t: None, stop,
                              interval=0)

    sampler.run()

    assert source.taken == 0


def test_sampler_gap() -> None:
    times = [START, START + timedelta(minutes=30)]

    reported, _ = run([here(), here(), here()], times)

    gaps = [c for c in reported if c.kind == EventKind.CLOCK_GAP]
    assert len(gaps) == 1
    assert gaps[0].payload["seconds"] >= 1799
    firsts = [c for c in reported if c.kind == EventKind.PRESENCE
              and c.payload.get("first")]
    assert len(firsts) == 2


def test_sampler_hour_end() -> None:
    times = [START, START + timedelta(seconds=3)]

    reported, _ = run([here(), here(), here()], times)

    (closed,) = [c for c in reported if c.kind == EventKind.APP_HOUR_CLOSED]
    assert closed.payload == {"hour_start": "2026-11-06T09:00:00+00:00"}


def test_sampler_failure_is_reported_once() -> None:
    reported, failed = run([here()], [START], failure="Cannot read.")

    assert failed == ["Cannot read."]
    assert reported == []
