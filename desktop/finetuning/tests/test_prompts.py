from pathlib import Path

import pytest

from finetuning import prompts
from src.domain.conversation import rules as conversation_rules


def test_cells_deterministic() -> None:
    assert prompts.cells("voice", 30, 4) == prompts.cells("voice", 30, 4)
    assert prompts.cells("voice", 30, 4) != prompts.cells("voice", 30, 5)


def test_cells_cover_every_situation_first() -> None:
    situations = {c.situation for c in prompts.cells("voice", 13, 1)}

    assert situations == {name for name, _ in prompts.SITUATIONS["voice"]}


def test_cells_cover_every_character() -> None:
    names = {c.character for c in prompts.cells("voice", 40, 1)}

    assert names == {"yuna", "rin", "mira", "shiori"}


def test_crisis_cells_have_no_mood() -> None:
    crisis = [c for c in prompts.cells("voice", 60, 1) if c.situation == "crisis"]

    assert crisis and all(c.mood is None for c in crisis)


def test_summary_cells_have_no_character() -> None:
    assert {c.character for c in prompts.cells("summary", 8, 1)} == {""}


def test_cell_ids_carry_seed() -> None:
    assert prompts.cells("tools", 2, 7)[1].id == "tools-s7-0002"


def test_unknown_job_raises() -> None:
    with pytest.raises(ValueError):
        prompts.cells("weather", 5, 1)


def test_count_below_one_raises() -> None:
    with pytest.raises(ValueError):
        prompts.cells("voice", 0, 1)


@pytest.mark.parametrize("job", ["voice", "interpretation", "tools", "summary"])
def test_render_prompt_fills_every_placeholder(job: str) -> None:
    text = prompts.render_prompt(job, prompts.cells(job, 3, 1))

    assert "{{" not in text
    assert "voice-s1" not in text or job == "voice"


def test_render_prompt_has_current_layer_1() -> None:
    text = prompts.render_prompt("voice", prompts.cells("voice", 2, 1))

    assert conversation_rules.LAYER_1 in text
    assert conversation_rules.mood_line("restless") in text


def test_render_prompt_lists_every_cell() -> None:
    batch = prompts.cells("interpretation", 5, 2)

    text = prompts.render_prompt("interpretation", batch)

    assert all(f"| {c.id} |" in text for c in batch)


def test_write_prompts_in_batches(tmp_path: Path) -> None:
    written = prompts.write_prompts("tools", 30, 1, tmp_path, batch=25)

    assert [p.name for p in written] == ["train-tools-s1-001.md",
                                         "train-tools-s1-002.md"]
