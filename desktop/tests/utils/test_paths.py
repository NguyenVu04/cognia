import sys
from pathlib import Path

import pytest

from src.utils import paths
from src.utils.paths import resource


def test_resource_missing_raises() -> None:
    with pytest.raises(FileNotFoundError):
        resource("no-such-file")


def test_install_dir_from_source() -> None:
    assert paths.install_dir() == Path(paths.__file__).resolve().parents[2]


def test_install_dir_frozen(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Cognia.exe"))

    assert paths.install_dir() == tmp_path
