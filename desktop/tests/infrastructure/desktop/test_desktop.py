import ctypes
from ctypes import wintypes

import pytest

from src.infrastructure.desktop.native_frame import (
    HTCLIENT,
    WM_NCCALCSIZE,
    WM_NCHITTEST,
    NativeFrame,
)
from src.infrastructure.desktop.startup import NAME, StartupEntry, StartupFailed


class FakeDwm:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple] = []

    def add_frame_styles(self, hwnd):
        self.calls.append(("styles", hwnd))

    def extend_frame(self, hwnd):
        if self.fail:
            raise OSError
        self.calls.append(("extend", hwnd))

    def round_corners(self, hwnd):
        self.calls.append(("round", hwnd))


def message(hwnd: int, kind: int, wparam: int = 1) -> int:
    msg = wintypes.MSG()
    msg.hWnd = hwnd
    msg.message = kind
    msg.wParam = wparam
    message.kept = msg  # keep it alive while the filter reads it
    return ctypes.addressof(msg)


def test_attach_sets_styles_and_extends_frame() -> None:
    api = FakeDwm()

    assert NativeFrame(api).attach(7)

    assert api.calls == [("styles", 7), ("extend", 7), ("round", 7)]


def test_attach_failure_returns_false() -> None:
    frame = NativeFrame(FakeDwm(fail=True))

    assert not frame.attach(7)
    assert frame.nativeEventFilter(b"windows_generic_MSG", message(7, WM_NCCALCSIZE)) \
        == (False, 0)


def test_calcsize_handled_only_for_attached_windows() -> None:
    frame = NativeFrame(FakeDwm())
    frame.attach(7)

    assert frame.nativeEventFilter(b"windows_generic_MSG", message(7, WM_NCCALCSIZE)) \
        == (True, 0)
    assert frame.nativeEventFilter(b"windows_generic_MSG", message(8, WM_NCCALCSIZE)) \
        == (False, 0)


def test_hit_test_is_client() -> None:
    frame = NativeFrame(FakeDwm())
    frame.attach(7)

    assert frame.nativeEventFilter(b"windows_generic_MSG", message(7, WM_NCHITTEST)) \
        == (True, HTCLIENT)


class FakeRunKey:
    def __init__(self, fail: bool = False) -> None:
        self.values: dict[str, str] = {}
        self.fail = fail

    def get(self, name):
        return self.values.get(name)

    def set(self, name, command):
        if self.fail:
            raise OSError
        self.values[name] = command

    def delete(self, name):
        self.values.pop(name, None)


def test_enable_writes_the_command_and_disable_removes_it() -> None:
    key = FakeRunKey()
    entry = StartupEntry('"pythonw.exe" "main.py" --background', key)

    entry.enable()
    assert key.values[NAME].endswith("--background")
    assert entry.enabled()
    entry.disable()

    assert not entry.enabled()


def test_failure_raises_startup_failed() -> None:
    with pytest.raises(StartupFailed):
        StartupEntry("x", FakeRunKey(fail=True)).enable()
