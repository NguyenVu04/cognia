"""The one key combination for talking, received from any application.

Windows sends a single message when the combination is pressed. No other key
is read: ``RegisterHotKey`` reports only the combination it was given.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312
_ID = 0xC061
_MODIFIERS = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "meta": 0x0008}
_MOD_NOREPEAT = 0x4000
_NAMED = {"space": 0x20, **{f"f{n}": 0x6F + n for n in range(1, 25)}}


def parse(sequence: str) -> tuple[int, int]:
    """The Windows modifiers and virtual key of a portable key sequence such as
    ``"Ctrl+Alt+Space"``. Raises ``ValueError`` for a key with no Ctrl, Alt or
    Win, or a key it does not know."""
    parts = [p.strip().lower() for p in sequence.split("+") if p.strip()]
    if not parts:
        raise ValueError("No key was given.")
    *mods, key = parts
    modifiers = 0
    for name in mods:
        if name not in _MODIFIERS:
            raise ValueError(f"Unknown modifier {name!r}.")
        modifiers |= _MODIFIERS[name]
    if not modifiers & (_MODIFIERS["ctrl"] | _MODIFIERS["alt"] | _MODIFIERS["meta"]):
        raise ValueError("The combination needs Ctrl, Alt or Win.")
    if key in _NAMED:
        return modifiers, _NAMED[key]
    if len(key) == 1 and key.isalnum():
        return modifiers, ord(key.upper())
    raise ValueError(f"Unknown key {key!r}.")


class _User32:
    """The two Win32 functions this module may call."""

    def __init__(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.register = user32.RegisterHotKey
        self.register.argtypes = (
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        )
        self.register.restype = wintypes.BOOL
        self.unregister = user32.UnregisterHotKey
        self.unregister.argtypes = (wintypes.HWND, ctypes.c_int)
        self.unregister.restype = wintypes.BOOL


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, owner: TalkHotkey) -> None:
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) != b"windows_generic_MSG" or not message:
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY and msg.wParam == _ID:
            self._owner.pressed.emit()
            return True, 0
        return False, 0


class TalkHotkey(QObject):
    pressed = Signal()

    def __init__(self, api=None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._hwnd = 0
        self.filter = _Filter(self)

    def register(self, hwnd: int, sequence: str) -> bool:
        """Listen for ``sequence`` on the window ``hwnd``. False if Windows
        refused it, for example because another application holds it."""
        self.unregister()
        try:
            modifiers, key = parse(sequence)
            if self._api is None:
                self._api = _User32()
        except (ValueError, OSError):
            return False
        if not self._api.register(hwnd, _ID, modifiers | _MOD_NOREPEAT, key):
            return False
        self._hwnd = hwnd
        return True

    def unregister(self) -> None:
        if self._hwnd and self._api is not None:
            self._api.unregister(self._hwnd, _ID)
        self._hwnd = 0
