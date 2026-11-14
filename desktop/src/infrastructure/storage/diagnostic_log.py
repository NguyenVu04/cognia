"""The error log as a group of data that can be counted and erased."""

from __future__ import annotations

from src.domain.ports import ErasureFailed
from src.utils import log

NOT_COUNTED = "The error log cannot be read, so nothing was erased."
NOT_ERASED = "The error log could not be erased. Try again."


class FileDiagnosticLog:
    """A :class:`~src.domain.ports.DiagnosticLog` over the log files."""

    def entries(self) -> int:
        try:
            return log.entries()
        except OSError as error:
            raise ErasureFailed(NOT_COUNTED) from error

    def erase(self) -> None:
        try:
            log.erase()
        except OSError as error:
            raise ErasureFailed(NOT_ERASED) from error
