import json
from datetime import date
from pathlib import Path

import pytest

from finetuning import export, train

ROWS = [{"id": str(i), "messages": [{"role": "user", "content": str(i)}]}
        for i in range(20)]


def test_read_rows(tmp_path: Path) -> None:
    path = tmp_path / "train.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in ROWS[:3]) + "\n\n", "utf-8")

    assert train.read_rows(path) == ROWS[:3]


def test_read_rows_refuses_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "train.jsonl"
    path.write_text("", "utf-8")

    with pytest.raises(ValueError, match="no examples"):
        train.read_rows(path)


def test_read_rows_refuses_row_without_messages(tmp_path: Path) -> None:
    path = tmp_path / "train.jsonl"
    path.write_text('{"id": "a"}\n', "utf-8")

    with pytest.raises(ValueError, match="Line 1"):
        train.read_rows(path)


def test_main_refuses_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "train.jsonl"
    path.write_text("", "utf-8")

    with pytest.raises(ValueError):
        train.main([str(path), str(tmp_path / "adapter")])


def test_split_deterministic() -> None:
    first = train.split(ROWS, 0.1, 7)

    assert first == train.split(ROWS, 0.1, 7)
    assert len(first[0]) == 18 and len(first[1]) == 2
    assert {r["id"] for r in first[0] + first[1]} == {r["id"] for r in ROWS}


def test_split_keeps_one_for_validation() -> None:
    assert len(train.split(ROWS[:3], 0.1, 1)[1]) == 1


def test_split_bounds() -> None:
    with pytest.raises(ValueError):
        train.split(ROWS, 1.0, 1)


def test_take_fraction_nested() -> None:
    small = train.take_fraction(ROWS, 0.25, 3)
    large = train.take_fraction(ROWS, 0.5, 3)

    assert small == large[: len(small)]


@pytest.mark.parametrize("fraction", [0, 1.5])
def test_take_fraction_bounds(fraction: float) -> None:
    with pytest.raises(ValueError):
        train.take_fraction(ROWS, fraction, 1)


def test_write_licences_notice(tmp_path: Path) -> None:
    licence = tmp_path / "LICENSE"
    licence.write_text("Apache License 2.0", "utf-8")

    export.write_licences(tmp_path / "out", licence, "base/model", date(2025, 12, 1))

    notice = (tmp_path / "out" / "NOTICE.txt").read_text("utf-8")
    assert "Base model: base/model" in notice
    assert "2025-12-01" in notice
    assert (tmp_path / "out" / "LICENSE.txt").read_text("utf-8") == "Apache License 2.0"


def test_name_chat_file_skips_mmproj(tmp_path: Path) -> None:
    (tmp_path / "model-Q4_K_M.gguf").write_bytes(b"x")
    (tmp_path / "mmproj-F16.gguf").write_bytes(b"y")

    named = export.name_chat_file(tmp_path)

    assert named == tmp_path / "chat.gguf"
    assert (tmp_path / "mmproj-F16.gguf").exists()


def test_name_chat_file_refuses_two(tmp_path: Path) -> None:
    (tmp_path / "a.gguf").write_bytes(b"x")
    (tmp_path / "b.gguf").write_bytes(b"y")

    with pytest.raises(ValueError, match="found 2"):
        export.name_chat_file(tmp_path)


def test_gguf_directory() -> None:
    assert export.gguf_directory(Path("out/merged")) == Path("out/merged_gguf")
