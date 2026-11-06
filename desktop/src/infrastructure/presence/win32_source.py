"""The four facts, read from Windows. The only code that asks Windows about the
user.

Win32 functions declared here, and no others:

- idle time: ``GetLastInputInfo``, ``GetTickCount64``
- lock state: ``WTSQuerySessionInformationW``, ``WTSFreeMemory``
- presentation state: ``SHQueryUserNotificationState``
- foreground application name: ``GetForegroundWindow``,
  ``GetWindowThreadProcessId``, ``OpenProcess``, ``QueryFullProcessImageNameW``,
  ``CloseHandle``

Nothing here reads a window title, a window position, a key, the clipboard or
the screen. The path of the program in front is cut to its file name at once.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import PureWindowsPath

from src.domain.ports import PresenceFailed, PresenceSample

NO_IDLE_TIME = (
    "Windows does not say how long since the mouse or keyboard was touched on "
    "this machine, so desk awareness stays off."
)

_WTS_CURRENT_SERVER = None
_WTS_CURRENT_SESSION = 0xFFFFFFFF
_WTS_SESSION_INFO_EX = 25
_WTS_SESSIONSTATE_LOCK = 0
# Level (4 bytes) and 4 bytes of padding, because the union after it holds an
# 8-byte LARGE_INTEGER; then SessionId (4) and SessionState (4).
_SESSION_FLAGS_OFFSET = 16
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN and QUNS_PRESENTATION_MODE all mean
# that the user should not be interrupted.
_PRESENTING = (2, 3, 4)
_PATH_CHARS = 1024


class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class Win32PresenceSource:
    """A :class:`~src.domain.ports.PresenceSource` for Windows 10 and 11."""

    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
        self._shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        self._declare()

    def _declare(self) -> None:
        u, k, w, s = self._user32, self._kernel32, self._wtsapi32, self._shell32
        u.GetLastInputInfo.argtypes = [ctypes.POINTER(_LastInput)]
        u.GetLastInputInfo.restype = wintypes.BOOL
        k.GetTickCount64.argtypes = []
        k.GetTickCount64.restype = ctypes.c_ulonglong
        w.WTSQuerySessionInformationW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD),
        ]
        w.WTSQuerySessionInformationW.restype = wintypes.BOOL
        w.WTSFreeMemory.argtypes = [ctypes.c_void_p]
        w.WTSFreeMemory.restype = None
        s.SHQueryUserNotificationState.argtypes = [ctypes.POINTER(ctypes.c_int)]
        s.SHQueryUserNotificationState.restype = ctypes.c_long
        u.GetForegroundWindow.argtypes = []
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
        ]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        k.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL

    def sample(self) -> PresenceSample:
        return PresenceSample(
            idle_seconds=self._idle_seconds(),
            locked=self._locked(),
            presenting=self._presenting(),
            foreground_app=self._foreground_app(),
        )

    def _idle_seconds(self) -> int:
        info = _LastInput(cbSize=ctypes.sizeof(_LastInput))
        if not self._user32.GetLastInputInfo(ctypes.byref(info)):
            raise PresenceFailed(NO_IDLE_TIME)
        # dwTime is the low 32 bits of the tick count, so it wraps every 49 days.
        now = self._kernel32.GetTickCount64() & 0xFFFFFFFF
        return ((now - info.dwTime) & 0xFFFFFFFF) // 1000

    def _locked(self) -> bool:
        buffer = ctypes.c_void_p()
        size = wintypes.DWORD()
        if not self._wtsapi32.WTSQuerySessionInformationW(
            _WTS_CURRENT_SERVER, _WTS_CURRENT_SESSION, _WTS_SESSION_INFO_EX,
            ctypes.byref(buffer), ctypes.byref(size),
        ):
            return False
        try:
            if size.value < _SESSION_FLAGS_OFFSET + 4:
                return False
            flags = ctypes.c_long.from_address(
                buffer.value + _SESSION_FLAGS_OFFSET
            ).value
            return flags == _WTS_SESSIONSTATE_LOCK
        finally:
            self._wtsapi32.WTSFreeMemory(buffer)

    def _presenting(self) -> bool:
        state = ctypes.c_int()
        if self._shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return False
        return state.value in _PRESENTING

    def _foreground_app(self) -> str:
        window = self._user32.GetForegroundWindow()
        if not window:
            return ""
        process_id = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
        if not process_id.value:
            return ""
        process = self._kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value
        )
        if not process:
            return ""
        try:
            path = ctypes.create_unicode_buffer(_PATH_CHARS)
            length = wintypes.DWORD(_PATH_CHARS)
            if not self._kernel32.QueryFullProcessImageNameW(
                process, 0, path, ctypes.byref(length)
            ):
                return ""
            return PureWindowsPath(path.value).name.casefold()
        finally:
            self._kernel32.CloseHandle(process)
