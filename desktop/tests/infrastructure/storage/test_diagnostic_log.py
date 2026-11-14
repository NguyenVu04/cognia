import logging
from pathlib import Path

import pytest

from src.domain.ports import ErasureFailed
from src.infrastructure.storage.diagnostic_log import (
    NOT_COUNTED,
    NOT_ERASED,
    FileDiagnosticLog,
)
from src.utils import log


@pytest.fixture
def started(tmp_path: Path):
    log.start(tmp_path / log.FILE_NAME)
    yield tmp_path / log.FILE_NAME
    log.stop()


def test_counts_the_lines(started: Path) -> None:
    logging.getLogger("src.tests").info("one")
    logging.getLogger("src.tests").info("two")

    assert FileDiagnosticLog().entries() == 2


def test_erase_leaves_no_line(started: Path) -> None:
    logging.getLogger("src.tests").info("one")

    FileDiagnosticLog().erase()

    assert FileDiagnosticLog().entries() == 0


def test_unreadable_log_is_an_erasure_failure(monkeypatch) -> None:
    def refuse() -> int:
        raise PermissionError("locked")

    monkeypatch.setattr(log, "entries", refuse)

    with pytest.raises(ErasureFailed, match=NOT_COUNTED):
        FileDiagnosticLog().entries()


def test_log_that_cannot_be_removed_is_an_erasure_failure(monkeypatch) -> None:
    def refuse() -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(log, "erase", refuse)

    with pytest.raises(ErasureFailed, match=NOT_ERASED):
        FileDiagnosticLog().erase()
