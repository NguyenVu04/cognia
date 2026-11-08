import sys
from pathlib import Path

from src.app.application import start_command


def test_start_command_from_source() -> None:
    assert start_command().endswith('__main__.py" --background')


def test_start_command_frozen(tmp_path: Path, monkeypatch) -> None:
    exe = tmp_path / "Cognia.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))

    assert start_command() == f'"{exe}" --background'
