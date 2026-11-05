import subprocess
import sys

import pytest

from src.infrastructure.ai.job_object import JobObject

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def sleeper() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_close_ends_assigned_process() -> None:
    job = JobObject()
    child = sleeper()
    job.assign(child.pid)

    job.close()

    assert child.wait(timeout=5) is not None


def test_close_twice_is_safe() -> None:
    job = JobObject()
    job.close()
    job.close()


def test_assign_unknown_process_raises() -> None:
    job = JobObject()
    child = sleeper()
    child.kill()
    child.wait()
    try:
        with pytest.raises(OSError):
            job.assign(child.pid)
    finally:
        job.close()
