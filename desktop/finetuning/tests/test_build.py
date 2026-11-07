import json
from pathlib import Path

import pytest

from finetuning.build import build
from finetuning.examples import write_examples
from finetuning.review import Decision, record

from .factories import tools, voice


def setup(tmp_path: Path, *accepted: str) -> Path:
    write_examples(tmp_path / "train" / "a.jsonl",
                   [voice(), voice(id="voice-2"), tools()])
    for example_id in accepted:
        record(tmp_path / "review.jsonl", Decision(example_id, "accepted", "t"))
    return tmp_path


def lines(out: Path) -> list[dict]:
    text = (out / "train.jsonl").read_text("utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_build_keeps_only_accepted(tmp_path: Path) -> None:
    counts = build(setup(tmp_path, "voice-1"), tmp_path / "out")

    assert counts == {"voice": 1}
    assert [row["id"] for row in lines(tmp_path / "out")] == ["voice-1"]


def test_build_applies_edit(tmp_path: Path) -> None:
    data = setup(tmp_path)
    record(data / "review.jsonl", Decision("voice-1", "accepted", "t", target="Hmph."))

    build(data, tmp_path / "out")

    assert lines(tmp_path / "out")[0]["messages"][-1]["content"] == "Hmph."


def test_build_refuses_leak(tmp_path: Path) -> None:
    data = setup(tmp_path, "voice-1")
    write_examples(data / "test" / "a.jsonl", [voice(id="t1")])

    with pytest.raises(ValueError, match="t1"):
        build(data, tmp_path / "out")


def test_build_refuses_accepted_with_error(tmp_path: Path) -> None:
    data = setup(tmp_path)
    record(data / "review.jsonl", Decision("voice-1", "accepted", "t", target=""))

    with pytest.raises(ValueError, match="voice-1"):
        build(data, tmp_path / "out")


def test_build_line_shape(tmp_path: Path) -> None:
    build(setup(tmp_path, "tools-1"), tmp_path / "out")

    [row] = lines(tmp_path / "out")
    roles = [m["role"] for m in row["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]
    assert len(row["tools"]) == 12
