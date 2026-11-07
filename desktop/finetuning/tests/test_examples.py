from datetime import date
from pathlib import Path

import pytest

from finetuning.examples import (
    ToolUse,
    Turn,
    check,
    check_no_leak,
    coverage,
    duplicate_ids,
    read_examples,
    validate,
    write_examples,
)

from .factories import interpretation, summary, tools, voice


def test_read_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    examples = [voice(), interpretation(), summary(), tools()]

    write_examples(path, examples)

    assert read_examples(path) == examples


def test_read_bad_line_names_line(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    write_examples(path, [voice(), voice(id="voice-2")])
    path.write_text(path.read_text("utf-8") + "{not json\n", "utf-8")

    with pytest.raises(ValueError, match="line 3"):
        read_examples(path)


def test_read_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    write_examples(path, [voice()])
    path.write_text("\n" + path.read_text("utf-8") + "\n\n", "utf-8")

    assert len(read_examples(path)) == 1


@pytest.mark.parametrize("example", [voice(), interpretation(), summary(), tools()])
def test_validate_good_examples(example) -> None:
    assert validate(example) == []


def test_validate_unknown_job() -> None:
    assert validate(voice(job="poem")) == ["job is not one of voice, interpretation, "
                                           "summary, tools"]


def test_validate_unknown_mood() -> None:
    assert any("mood" in e for e in validate(voice(mood="angry")))


def test_validate_unknown_character() -> None:
    assert any("character" in e for e in validate(voice(character="zoe")))


def test_validate_two_user_turns_in_row() -> None:
    history = (Turn(True, "Hi"), Turn(True, "Hello?"), Turn(False, "Hm."))

    assert any("two messages in a row" in e for e in validate(voice(history=history)))


def test_validate_history_must_end_with_companion() -> None:
    errors = validate(voice(history=(Turn(True, "Hi"),)))

    assert any("must end with the companion" in e for e in errors)


def test_validate_interpretation_missing_field() -> None:
    target = dict(interpretation().target)
    del target["confidence"]

    assert "target lacks confidence" in validate(interpretation(target=target))


def test_validate_interpretation_bad_values() -> None:
    target = dict(interpretation().target, importance=11, event_class="joy",
                  confidence=1.5)

    errors = validate(interpretation(target=target))

    assert len(errors) == 3


def test_validate_unknown_tool() -> None:
    errors = validate(tools(calls=(ToolUse("weather"),)))

    assert errors == ["no tool is called 'weather'"]


def test_validate_tool_lacks_argument() -> None:
    assert validate(tools(calls=(ToolUse("calculate"),))) == [
        "calculate lacks expression"
    ]


def test_validate_crisis_target_must_comply() -> None:
    example = voice(crisis=True, mood=None, target="Please talk to someone.")

    assert any("fictional character" in e for e in validate(example))


def test_validate_crisis_has_no_mood() -> None:
    example = voice(
        crisis=True,
        target="I'm a fictional character, and I can't take the place of a real "
        "person. Please reach out to someone you trust.",
    )

    assert validate(example) == ["a crisis turn has no mood"]


def test_validate_long_reasoning() -> None:
    assert any("reasoning" in e for e in validate(voice(reasoning="x" * 401)))


def test_validate_test_needs_expect() -> None:
    assert validate(voice(), test=True) == ["expect lacks asks_mood"]
    assert validate(voice(target=None, expect={"asks_mood": False}), test=True) == []


def test_validate_train_voice_needs_target() -> None:
    assert validate(voice(target=None)) == ["target is empty"]


def test_coverage_counts() -> None:
    counts = coverage([voice(), voice(id="v2", character="yuna"), tools()])

    assert counts["voice"] == 2
    assert counts["voice/character/rin"] == 1
    assert counts["voice/tag/good_news"] == 2
    assert counts["tools/mood/lively"] == 1


def test_duplicate_ids() -> None:
    assert duplicate_ids([voice(), voice(), tools()]) == ["voice-1"]


def test_check_no_leak() -> None:
    with pytest.raises(ValueError, match="voice-9"):
        check_no_leak([voice()], [voice(id="voice-9", message="i PASSED my  driving "
                                        "test!")])


def test_check_no_leak_passes() -> None:
    check_no_leak([voice()], [voice(id="voice-9", message="Something else.")])


def test_check_counts_failures(tmp_path: Path, capsys) -> None:
    write_examples(tmp_path / "train" / "a.jsonl", [voice(), voice(mood="angry",
                                                                   id="v2")])
    write_examples(tmp_path / "test" / "a.jsonl", [voice(id="t1", today=date(
        2026, 11, 8), expect={"asks_mood": False}, message="Different.")])

    assert check(tmp_path) == 1
    assert "ERROR train/v2" in capsys.readouterr().out
