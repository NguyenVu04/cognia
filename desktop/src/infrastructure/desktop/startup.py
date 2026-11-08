"""Starting with Windows, through the Run key of the current user.

The key is the only place this choice is kept: the user can also change it in
the Windows settings, and Cognia reads it back from there.
"""

from __future__ import annotations

from typing import Protocol

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Cognia"
NOT_CHANGED = "Windows did not let me change how I start. Nothing was changed."


class StartupFailed(Exception):
    """The Run key could not be changed, with a sentence saying so."""


class RunKey(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, command: str) -> None: ...
    def delete(self, name: str) -> None: ...


class _Registry:
    def _open(self, write: bool):
        import winreg

        access = winreg.KEY_SET_VALUE if write else winreg.KEY_READ
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, access)

    def get(self, name: str) -> str | None:
        import winreg

        try:
            with self._open(False) as key:
                return str(winreg.QueryValueEx(key, name)[0])
        except FileNotFoundError:
            return None

    def set(self, name: str, command: str) -> None:
        import winreg

        with self._open(True) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)

    def delete(self, name: str) -> None:
        import winreg

        try:
            with self._open(True) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass


class StartupEntry:
    """Whether Cognia starts with Windows, with ``command`` as its start line."""

    def __init__(self, command: str, registry: RunKey | None = None) -> None:
        self._command = command
        self._registry = registry or _Registry()

    def enabled(self) -> bool:
        try:
            return self._registry.get(NAME) is not None
        except OSError:
            return False

    def enable(self) -> None:
        try:
            self._registry.set(NAME, self._command)
        except OSError as error:
            raise StartupFailed(NOT_CHANGED) from error

    def disable(self) -> None:
        try:
            self._registry.delete(NAME)
        except OSError as error:
            raise StartupFailed(NOT_CHANGED) from error
