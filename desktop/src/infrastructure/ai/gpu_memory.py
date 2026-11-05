"""The dedicated video memory of each graphics adapter, as Windows reports it.

llama-server reports the memory a GPU can reach, and for a GPU built into the
processor that is shared system memory, often more than a separate GPU holds.
DXGI separates the two: an integrated GPU has little or no dedicated memory.

The only Win32 calls: CreateDXGIFactory1, and the COM methods
IDXGIFactory1::EnumAdapters1, IDXGIAdapter1::GetDesc1 and IUnknown::Release.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

_RELEASE = 2
_ENUM_ADAPTERS1 = 12
_GET_DESC1 = 10
# Microsoft Basic Render Driver, which draws on the CPU.
_SOFTWARE_ADAPTER = 2


class _Guid(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _Luid(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _AdapterDesc1(ctypes.Structure):
    _fields_ = [
        ("Description", wintypes.WCHAR * 128),
        ("VendorId", wintypes.UINT),
        ("DeviceId", wintypes.UINT),
        ("SubSysId", wintypes.UINT),
        ("Revision", wintypes.UINT),
        ("DedicatedVideoMemory", ctypes.c_size_t),
        ("DedicatedSystemMemory", ctypes.c_size_t),
        ("SharedSystemMemory", ctypes.c_size_t),
        ("AdapterLuid", _Luid),
        ("Flags", wintypes.UINT),
    ]


_IID_FACTORY1 = _Guid(
    0x770AAE78, 0xF26F, 0x4DBA,
    (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87),
)


def name_key(name: str) -> str:
    """The form in which DXGI and Vulkan names are compared."""
    return " ".join(name.split()).casefold()


def dedicated_memory() -> dict[str, int]:
    """Bytes of dedicated video memory by adapter name, in :func:`name_key`
    form. Empty if Windows cannot list the adapters."""
    try:
        dxgi = ctypes.WinDLL("dxgi")
    except OSError:
        return {}
    create = dxgi.CreateDXGIFactory1
    create.argtypes = (ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p))
    create.restype = ctypes.c_long
    factory = ctypes.c_void_p()
    if create(ctypes.byref(_IID_FACTORY1), ctypes.byref(factory)) != 0:
        return {}
    found: dict[str, int] = {}
    try:
        enum = _method(
            factory, _ENUM_ADAPTERS1, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p)
        )
        index = 0
        # Any failure ends the list; the last adapter answers "not found".
        while True:
            adapter = ctypes.c_void_p()
            if enum(factory, index, ctypes.byref(adapter)) != 0:
                break
            try:
                desc = _AdapterDesc1()
                get = _method(adapter, _GET_DESC1, ctypes.POINTER(_AdapterDesc1))
                if get(adapter, ctypes.byref(desc)) == 0 and not (
                    desc.Flags & _SOFTWARE_ADAPTER
                ):
                    found[name_key(desc.Description)] = desc.DedicatedVideoMemory
            finally:
                _release(adapter)
            index += 1
    finally:
        _release(factory)
    return found


def _method(obj: ctypes.c_void_p, index: int, *argtypes):
    """Method ``index`` of the COM object's table, callable with the object first."""
    table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    prototype = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return prototype(table[index])


def _release(obj: ctypes.c_void_p) -> None:
    if obj:
        _method(obj, _RELEASE)(obj)
