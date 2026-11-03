import json
from dataclasses import replace

import pytest

from src.domain.safety import rules as safety_rules
from training import generate
from training.generate import Example, Turn

CRISIS = "I want to kill myself"


def voice(character: str = "alpha", user: str = "hello", **changes) -> Example:
    example = Example(
        job="voice",
        character=character,
        turns=(Turn("u", user),),
        reasoning="reason",
        target="reply",
        cell="a",
    )
    return replace(example, **changes)


def interpretation(**answer) -> Example:
    target = {
        "event_class": "good_news",
        "confidence": 0.5,
        "importance": 5,
        "crisis": False,
        "facts": [],
        "commitments": [],
        "style_request": None,
    }
    return voice(job="interpretation", target=json.dumps({**target, **answer}))


def answers(*values: str):
    pending = iter(values)
    return lambda _prompt: next(pending)


def test_make_cells_is_the_full_product() -> None:
    cells = generate.make_cells("ab", "cd", "ef", "gh")

    assert len(set(cells)) == 16


def test_validate_accepts_voice_example() -> None:
    assert generate.validate(voice()) == []


def test_validate_accepts_interpretation_example() -> None:
    assert generate.validate(interpretation()) == []


def test_validate_refuses_unknown_job() -> None:
    assert generate.validate(voice(job="chat"))


def test_validate_refuses_empty_reasoning() -> None:
    assert generate.validate(voice(reasoning=""))


def test_validate_refuses_last_turn_from_companion() -> None:
    assert generate.validate(voice(turns=(Turn("c", "hello"),)))


def test_validate_refuses_think_tag_in_target() -> None:
    assert generate.validate(voice(target="[THINK]reply"))


def test_validate_refuses_unknown_event_class() -> None:
    assert generate.validate(interpretation(event_class="joy"))


@pytest.mark.parametrize("importance", [0, 11])
def test_validate_refuses_importance_outside_range(importance: int) -> None:
    assert generate.validate(interpretation(importance=importance))


def test_validate_accepts_style_request_text() -> None:
    assert generate.validate(interpretation(style_request="shorter")) == []


def test_validate_refuses_style_request_not_text() -> None:
    assert len(generate.validate(interpretation(style_request=3))) == 1


def test_validate_refuses_blank_style_request() -> None:
    assert len(generate.validate(interpretation(style_request="  "))) == 1


def test_validate_refuses_unknown_answer_key() -> None:
    errors = generate.validate(interpretation(closes_commitment=None))

    assert len(errors) == 1
    assert "closes_commitment" in errors[0]


def test_validate_refuses_malformed_interpretation() -> None:
    assert generate.validate(voice(job="interpretation", target="not json"))


def test_validate_accepts_crisis_voice_example() -> None:
    example = voice(
        user=CRISIS,
        instruction=safety_rules.instruction(),
        target=safety_rules.required_line(),
    )

    assert generate.validate(example) == []


def test_validate_refuses_tripwire_without_instruction() -> None:
    assert len(generate.validate(voice(user=CRISIS))) == 1


def test_validate_refuses_crisis_reply_that_does_not_comply() -> None:
    example = voice(
        user=CRISIS, instruction=safety_rules.instruction(), target="I'm here for you."
    )

    assert len(generate.validate(example)) == 1


def test_validate_checks_reply_when_only_the_model_found_a_crisis() -> None:
    example = voice(
        user="I gave my things away. Won't need them.",
        instruction=safety_rules.instruction(),
    )

    assert len(generate.validate(example)) == 1


def test_validate_skips_safety_on_interpretation() -> None:
    example = replace(interpretation(crisis=False), turns=(Turn("u", CRISIS),))

    assert generate.validate(example) == []


def test_read_write_round_trip(tmp_path) -> None:
    path = tmp_path / "examples.jsonl"
    examples = [voice(remembered=("a cat",)), voice("beta", mood="pleased")]

    generate.write_examples(path, examples)

    assert generate.read_examples(path) == examples


def test_read_reports_line_number_on_bad_json(tmp_path) -> None:
    path = tmp_path / "examples.jsonl"
    generate.write_examples(path, [voice()])
    with path.open("a", encoding="utf-8") as file:
        file.write("{broken\n")

    with pytest.raises(ValueError, match="line 2"):
        generate.read_examples(path)


def test_coverage_counts_each_cell() -> None:
    examples = [voice(cell="a"), voice(cell="a"), voice(cell="b")]

    assert generate.coverage(examples) == {"a": 2, "b": 1}


def test_split_keeps_a_character_on_one_side() -> None:
    examples = [voice(name) for name in "abcd" for _ in range(3)]

    train, val = generate.split(examples, 0.25, seed=1)

    assert train and val
    assert not {e.character for e in train} & {e.character for e in val}
    assert len(train) + len(val) == len(examples)


def test_split_is_stable_for_one_seed() -> None:
    examples = [voice(name) for name in "abcdefgh"]

    assert generate.split(examples, 0.25, 7) == generate.split(examples, 0.25, 7)


def test_split_refuses_a_single_character() -> None:
    with pytest.raises(ValueError):
        generate.split([voice(), voice()], 0.5, seed=1)


def test_check_no_leak_refuses_shared_character() -> None:
    with pytest.raises(ValueError, match="characters"):
        generate.check_no_leak([voice("alpha", "one")], [voice("alpha", "two")])


def test_check_no_leak_refuses_shared_user_message() -> None:
    with pytest.raises(ValueError, match="messages"):
        generate.check_no_leak([voice("alpha", "one")], [voice("beta", "one")])


def test_check_no_leak_accepts_separate_sets() -> None:
    generate.check_no_leak([voice("alpha", "one")], [voice("beta", "two")])


def test_review_keeps_accepted_and_drops_rejected(tmp_path) -> None:
    source, kept = tmp_path / "source.jsonl", tmp_path / "kept.jsonl"
    generate.write_examples(source, [voice("alpha"), voice("beta")])

    accepted = generate.review(source, kept, answers("a", "r"))

    assert accepted == 1
    assert generate.read_examples(kept) == [voice("alpha", reviewed=True)]


def test_review_resumes_after_stop(tmp_path) -> None:
    source, kept = tmp_path / "source.jsonl", tmp_path / "kept.jsonl"
    generate.write_examples(source, [voice("alpha"), voice("beta"), voice("gamma")])

    generate.review(source, kept, answers("a", "r", "q"))
    accepted = generate.review(source, kept, answers("a"))

    assert accepted == 1
    assert [e.character for e in generate.read_examples(kept)] == ["alpha", "gamma"]


def test_review_asks_again_after_an_unknown_answer(tmp_path) -> None:
    source, kept = tmp_path / "source.jsonl", tmp_path / "kept.jsonl"
    generate.write_examples(source, [voice()])

    assert generate.review(source, kept, answers("x", "a")) == 1


def test_main_validate_returns_one_on_bad_file(tmp_path) -> None:
    path = tmp_path / "examples.jsonl"
    generate.write_examples(path, [voice(reasoning="")])

    assert generate.main(["validate", str(path)]) == 1


def test_main_validate_returns_zero_on_good_file(tmp_path) -> None:
    path = tmp_path / "examples.jsonl"
    generate.write_examples(path, [voice()])

    assert generate.main(["validate", str(path)]) == 0
