"""The port through which the error log is counted and erased."""

from __future__ import annotations

from typing import Protocol


class DiagnosticLog(Protocol):
    """The error log of the application. It can hold the user's words, so it is
    erased with everything remembered. Each method raises
    :class:`~src.domain.ports.ErasureFailed` if it cannot do its work."""

    def entries(self) -> int:
        """The lines the log holds."""
        ...

    def erase(self) -> None:
        """Remove every line."""
        ...
