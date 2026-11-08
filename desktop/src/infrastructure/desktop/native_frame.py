"""The shadow and rounded corners of Windows for frameless windows.

Windows draws the shadow itself, so a window that repaints pays nothing for
it. A frameless window gets the frame styles back, its whole area becomes the
client area, and the frame extends one pixel into it.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
HTCLIENT = 1
GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WS_CAPTION = 0x00C00000
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


class _Margins(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_int),
        ("right", ctypes.c_int),
        ("top", ctypes.c_int),
        ("bottom", ctypes.c_int),
    ]


class DwmApi:
    """The five Win32 functions this module may call."""

    def __init__(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        dwmapi = ctypes.WinDLL("dwmapi")
        self._get_style = user32.GetWindowLongPtrW
        self._get_style.argtypes = (wintypes.HWND, ctypes.c_int)
        self._get_style.restype = ctypes.c_ssize_t
        self._set_style = user32.SetWindowLongPtrW
        self._set_style.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
        self._set_style.restype = ctypes.c_ssize_t
        self._set_pos = user32.SetWindowPos
        self._set_pos.argtypes = (
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        )
        self._extend = dwmapi.DwmExtendFrameIntoClientArea
        self._extend.argtypes = (wintypes.HWND, ctypes.POINTER(_Margins))
        self._attribute = dwmapi.DwmSetWindowAttribute
        self._attribute.argtypes = (
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        )

    def add_frame_styles(self, hwnd: int) -> None:
        style = self._get_style(hwnd, GWL_STYLE)
        self._set_style(hwnd, GWL_STYLE, style | WS_THICKFRAME | WS_CAPTION)
        self._set_pos(
            hwnd,
            None,
            0,
            0,
            0,
            0,
            SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER,
        )

    def extend_frame(self, hwnd: int) -> None:
        margins = _Margins(1, 1, 1, 1)
        if self._extend(hwnd, ctypes.byref(margins)) != 0:
            raise OSError("DwmExtendFrameIntoClientArea failed")

    def round_corners(self, hwnd: int) -> None:
        # Windows 10 does not know the attribute; its windows stay square.
        preference = ctypes.c_int(DWMWCP_ROUND)
        self._attribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )


class NativeFrame(QAbstractNativeEventFilter):
    """Install on the application with ``installNativeEventFilter``, then
    :meth:`attach` each frameless window once it has a handle."""

    def __init__(self, api: DwmApi | None = None) -> None:
        super().__init__()
        self._api = api
        self._windows: set[int] = set()

    def attach(self, hwnd: int) -> bool:
        """Give ``hwnd`` the native shadow. False if Windows refused; the
        window then keeps its own border."""
        if hwnd in self._windows:
            return True
        try:
            if self._api is None:
                self._api = DwmApi()
            self._api.add_frame_styles(hwnd)
            self._api.extend_frame(hwnd)
            self._api.round_corners(hwnd)
        except (OSError, AttributeError):
            return False
        self._windows.add(hwnd)
        return True

    def detach(self, hwnd: int) -> None:
        self._windows.discard(hwnd)

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) != b"windows_generic_MSG" or not message:
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.hWnd is None or int(msg.hWnd) not in self._windows:
            return False, 0
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            return True, 0
        if msg.message == WM_NCHITTEST:
            return True, HTCLIENT
        return False, 0
