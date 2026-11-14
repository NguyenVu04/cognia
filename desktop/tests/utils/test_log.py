import logging
import sys
import threading
from pathlib import Path

import pytest

from src.utils import log

logger = logging.getLogger("src.tests.log")


@pytest.fixture
def path(tmp_path: Path):
    file = tmp_path / "data" / log.FILE_NAME
    log.start(file)
    yield file
    log.stop()


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_entries_zero_before_start() -> None:
    assert log.entries() == 0


def test_start_writes_a_line(path: Path) -> None:
    logger.info("chat server ready in %.1f s", 4.2)

    assert "INFO" in text(path)
    assert "chat server ready in 4.2 s" in text(path)


def test_library_lines_stay_out(path: Path) -> None:
    logging.getLogger("httpx").warning("a library line")
    logger.info("an application line")

    assert "a library line" not in text(path)


def test_unhandled_exception_is_logged(path: Path, capsys) -> None:
    try:
        raise ValueError("no such table: x")
    except ValueError:
        sys.excepthook(*sys.exc_info())

    written = text(path)
    assert "Unhandled error" in written
    assert "ValueError: no such table: x" in written
    assert "test_log.py" in written


def test_thread_exception_is_logged(path: Path) -> None:
    def fail() -> None:
        raise RuntimeError("thread broke")

    thread = threading.Thread(target=fail, name="cognia-test")
    thread.start()
    thread.join()

    written = text(path)
    assert "Unhandled error in thread cognia-test" in written
    assert "RuntimeError: thread broke" in written


def test_stop_puts_the_hooks_back(tmp_path: Path) -> None:
    before = (sys.excepthook, threading.excepthook)
    log.start(tmp_path / log.FILE_NAME)

    log.stop()

    assert (sys.excepthook, threading.excepthook) == before


def test_rotates_keeping_one_old_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(log, "MAX_BYTES", 2000)
    file = tmp_path / log.FILE_NAME
    log.start(file)
    try:
        for number in range(200):
            logger.info("line %03d %s", number, "x" * 60)
    finally:
        log.stop()

    names = sorted(found.name for found in tmp_path.iterdir())
    assert names == [log.FILE_NAME, f"{log.FILE_NAME}.1"]
    assert file.stat().st_size <= 2000


def test_entries_counts_both_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(log, "MAX_BYTES", 2000)
    file = tmp_path / log.FILE_NAME
    log.start(file)
    try:
        for number in range(30):
            logger.info("line %03d %s", number, "x" * 60)
        older = file.with_name(f"{file.name}.1")
        lines = len(text(file).splitlines()) + len(text(older).splitlines())

        assert older.exists()
        assert log.entries() == lines
    finally:
        log.stop()


def test_erase_removes_both_files_and_logging_continues(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(log, "MAX_BYTES", 2000)
    file = tmp_path / log.FILE_NAME
    log.start(file)
    try:
        for number in range(30):
            logger.info("line %03d %s", number, "x" * 60)

        log.erase()

        assert log.entries() == 0
        assert not file.with_name(f"{file.name}.1").exists()
        logger.info("after the erasure")
        assert text(file).count("\n") == 1
        assert "after the erasure" in text(file)
    finally:
        log.stop()


def test_erase_before_start_does_nothing() -> None:
    log.erase()
