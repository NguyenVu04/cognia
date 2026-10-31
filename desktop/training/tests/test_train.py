from dataclasses import replace

import pytest

from src.domain.conversation import rules
from training import generate, train
from training.generate import Example, Turn


def voice(**changes) -> Example:
    example = Example(
        job="voice",
        character="A dry archivist",
        turns=(Turn("u", "one"), Turn("c", "two"), Turn("u", "three")),
        reasoning="reason",
        target="reply",
        cell="a",
        reviewed=True,
    )
    return replace(example, **changes)


def test_load_reviewed_returns_reviewed_items(tmp_path) -> None:
    path = tmp_path / "examples.jsonl"
    generate.write_examples(path, [voice()])

    assert train.load_reviewed(path) == [voice()]


def test_load_reviewed_refuses_unreviewed_item(tmp_path) -> None:
    path = tmp_path / "examples.jsonl"
    generate.write_examples(path, [voice(reviewed=False)])

    with pytest.raises(ValueError, match="not been reviewed"):
        train.load_reviewed(path)


def test_load_reviewed_refuses_invalid_item(tmp_path) -> None:
    path = tmp_path / "examples.jsonl"
    generate.write_examples(path, [voice(reasoning="")])

    with pytest.raises(ValueError, match="reasoning"):
        train.load_reviewed(path)


def test_take_fraction_half() -> None:
    assert len(train.take_fraction([voice()] * 100, 0.5, seed=1)) == 50


def test_take_fraction_full_keeps_all() -> None:
    assert len(train.take_fraction([voice()] * 100, 1.0, seed=1)) == 100


def test_take_fraction_small_share_is_part_of_large_share() -> None:
    examples = [voice(cell=str(number)) for number in range(10)]

    half = train.take_fraction(examples, 0.5, seed=1)

    assert half == train.take_fraction(examples, 1.0, seed=1)[:5]


def test_take_fraction_refuses_zero() -> None:
    with pytest.raises(ValueError):
        train.take_fraction([voice()], 0.0, seed=1)


def test_to_messages_starts_with_system_text() -> None:
    first = train.to_messages(voice())[0]

    assert first["role"] == "system"
    assert rules.system_text("A dry archivist") in first["content"]
    assert train.REASONING_RULE in first["content"]


def test_to_messages_maps_roles() -> None:
    roles = [message["role"] for message in train.to_messages(voice())]

    assert roles == ["system", "user", "assistant", "user", "assistant"]


def test_to_messages_adds_layer_4_to_last_user_turn() -> None:
    messages = train.to_messages(voice(mood="pleased"))

    assert messages[1]["content"] == "one"
    assert messages[3]["content"] == "three\n\nYour mood: pleased."


def test_to_messages_skips_empty_layer_4() -> None:
    assert train.to_messages(voice())[3]["content"] == "three"


def test_to_messages_puts_reasoning_on_last_assistant_only() -> None:
    messages = train.to_messages(voice())

    assert messages[-1]["reasoning_content"] == "reason"
    assert not any("reasoning_content" in message for message in messages[:-1])


def test_to_messages_keeps_tags_out_of_content() -> None:
    assert "[THINK]" not in train.to_messages(voice())[-1]["content"]
