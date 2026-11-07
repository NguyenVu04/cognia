"""The prompts that ask a large model for training examples.

Each prompt is a template in ``finetuning/prompts/`` filled with the
application's current wording, the characters, a few reviewed seed examples
and a batch of cells: one cell asks for one example. The person pastes each
prompt into a chat and saves the answer as a ``.jsonl`` file in
``finetuning/data/train/``.

Run from ``desktop/``:

    uv run python -m finetuning.prompts voice --count 100 --seed 1
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import product
from pathlib import Path

from finetuning.examples import JOBS, MOODS, read_folder, to_json
from finetuning.render import templates
from src.domain.conversation import rules as conversation_rules
from src.domain.safety import rules as safety_rules
from src.domain.tools import catalog

PROMPT_DIR = Path(__file__).parent / "prompts"
SEED_DIR = Path(__file__).parent / "data" / "seeds"
BATCH = 25

# What each cell asks for. The tag names the fault that the cell trains
# against, so the coverage shows each one.
SITUATIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "voice": (
        ("good_news", "The user shares good news about themselves."),
        ("bad_news", "The user shares bad news about themselves."),
        ("shared_worry", "The user shares a worry."),
        ("praise", "The user thanks or praises the companion."),
        ("complaint", "The user complains about the companion."),
        ("small_talk", "Small talk with no news, such as the weather or lunch."),
        ("asks_feeling", "The user asks how the companion feels. Only here may the "
         "reply name the mood."),
        ("mood_unasked", "A message that does not ask about feelings, under a "
         "strong mood. The mood shows only in rhythm and word choice."),
        ("remembered", "The message touches a remembered line. Use the line "
         "naturally, and never say the day it was told."),
        ("stored_line", "The user states a lasting fact, and `stored` holds the line "
         "just stored. Quote it once, exactly, in quotation marks, and invite a "
         "correction in a few words. Do not repeat the whole message."),
        ("odd_turn", "An odd turn: the user repeats a pasted text, tests the "
         "companion, or asks whether it is an AI or has feelings. Stay in "
         "character."),
        ("question", "The user asks for an opinion or advice that needs no tool."),
        ("crisis", "The user writes about harming themselves, or about a crisis. Set "
         "crisis to true and mood to null."),
    ),
    "interpretation": (
        ("question", "A question. No fact."),
        ("thanks", "Thanks or praise for the companion. No fact."),
        ("request", "A request to do something together, or a request for help. "
         "No fact."),
        ("story", "A piece of a story about one day, such as a walk. No fact "
         "unless it states something lasting about the user."),
        ("lasting_fact", "A lasting fact about the user: work, study, family, a pet, "
         "a habit, a plan with a date."),
        ("passing_mood", "A passing mood or state, such as being tired today. No "
         "fact."),
        ("mixed", "A lasting fact inside a longer message with a question."),
        ("contradicts_known", "A new fact that disagrees with a line in `known`. Keep "
         "the new fact."),
        ("already_known", "A fact that is already a line in `known`. No new fact."),
        ("good_news", "Good news about the user."),
        ("bad_news", "Bad news about the user."),
        ("shared_worry", "A worry."),
        ("complaint", "A complaint about the companion."),
        ("crisis", "A message about harming themselves or a crisis, sometimes with "
         "no obvious word such as 'suicide'."),
    ),
    "tools": (
        *((spec.name, f"A message that needs the tool `{spec.name}`.")
          for spec in catalog.SPECS),
        ("two_tools", "A message that needs two different tools, one after the "
         "other."),
        ("no_tool", "A message that sounds close to a tool but needs none, such as "
         "talk about time or feelings with no question. `calls` is empty."),
        ("no_tool_world", "A question about the world outside the machine, such as "
         "news or prices. No tool; say you can't know that from here, and offer to "
         "open a search."),
    ),
    "summary": (
        ("short", "A conversation of 6 to 10 messages."),
        ("medium", "A conversation of 12 to 20 messages."),
        ("long", "A conversation of 24 to 36 messages."),
        ("with_previous", "8 to 14 messages and an earlier summary to merge."),
    ),
}
_HISTORY = (0, 2, 4)
# The day of each example varies, so the model does not learn one date.
_FIRST_DAY = date(2026, 1, 1)
_DAYS = 547


@dataclass(frozen=True)
class Cell:
    """One example to ask for."""

    id: str
    today: date
    character: str
    mood: str | None
    situation: str
    detail: str
    history_turns: int


def cells(job: str, count: int, seed: int) -> list[Cell]:
    """``count`` cells of ``job``. The situations take turns, so a small batch
    still covers them, and each spreads over the characters, moods and history
    lengths. The same arguments always give the same cells. Raises
    ``ValueError`` for an unknown job or a count below 1."""
    if job not in JOBS:
        raise ValueError(f"No job is called {job!r}.")
    if count < 1:
        raise ValueError("The count must be 1 or more.")
    rng = random.Random(seed)
    names = sorted(templates()) if job != "summary" else [""]
    moods: Sequence[str | None] = MOODS if job in ("voice", "tools") else (None,)
    turns = _HISTORY if job != "summary" else (0,)
    queues = []
    for situation in SITUATIONS[job]:
        grid = list(product(names, moods, turns))
        rng.shuffle(grid)
        queues.append((situation, grid))
    result = []
    for number in range(count):
        (situation, detail), grid = queues[number % len(queues)]
        name, mood, history = grid[number // len(queues) % len(grid)]
        today = _FIRST_DAY + timedelta(days=rng.randrange(_DAYS))
        result.append(
            Cell(
                f"{job}-s{seed}-{number + 1:04d}",
                today,
                name,
                None if situation == "crisis" else mood,
                situation,
                detail,
                history,
            )
        )
    return result


def _characters_text() -> str:
    parts = []
    for template in templates().values():
        parts.append(f"### {template.id} ({template.name}, {template.role})\n\n"
                     f"{template.description.strip()}")
    return "\n\n".join(parts)


def _moods_text() -> str:
    return "\n".join(
        f"- {name}: \"{conversation_rules.mood_line(name)}\"" for name in MOODS
    )


def _tools_text() -> str:
    return "\n".join(
        f"- `{spec.name}`: {spec.description} Arguments: "
        f"{json.dumps(spec.parameters.get('properties', {}))}"
        for spec in catalog.SPECS
    )


def _seeds_text(job: str) -> str:
    seeds = [e for e in read_folder(SEED_DIR) if e.job == job]
    if not seeds:
        return "(none yet)"
    return "\n".join(json.dumps(to_json(e), ensure_ascii=False) for e in seeds)


def _cells_text(batch: Sequence[Cell]) -> str:
    rows = [
        "| id | today | character | mood | situation | earlier turns |",
        "|---|---|---|---|---|---|",
    ]
    rows += [
        f"| {c.id} | {c.today.isoformat()} | {c.character or '-'} | "
        f"{c.mood or 'null'} | {c.situation}: {c.detail} | {c.history_turns} |"
        for c in batch
    ]
    return "\n".join(rows)


def render_prompt(job: str, batch: Sequence[Cell]) -> str:
    """The prompt that asks for one example for each cell of ``batch``. Raises
    ``ValueError`` for an unknown job."""
    if job not in JOBS:
        raise ValueError(f"No job is called {job!r}.")
    template = (PROMPT_DIR / f"{job}.md").read_text("utf-8")
    values = {
        "LAYER_1": conversation_rules.LAYER_1,
        "REASONING_RULE": conversation_rules.REASONING_RULE,
        "CHARACTERS": _characters_text(),
        "MOOD_LINES": _moods_text(),
        "TOOLS": _tools_text(),
        "CRISIS_INSTRUCTION": safety_rules.instruction(),
        "INTERPRETATION_INSTRUCTION": conversation_rules.interpretation_instruction(
            batch[0].today, ["<each line of `known`>"]
        ),
        "SUMMARY_SYSTEM": conversation_rules.SUMMARY_SYSTEM,
        "SEEDS": _seeds_text(job),
        "CELLS": _cells_text(batch),
        "COUNT": str(len(batch)),
    }
    text = template
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def write_prompts(
    job: str, count: int, seed: int, out: Path, batch: int = BATCH
) -> list[Path]:
    """Write the prompts for ``count`` cells, ``batch`` cells a file, and return
    their paths."""
    out.mkdir(parents=True, exist_ok=True)
    every = cells(job, count, seed)
    written = []
    for number, start in enumerate(range(0, len(every), batch), 1):
        path = out / f"train-{job}-s{seed}-{number:03d}.md"
        path.write_text(render_prompt(job, every[start:start + batch]), "utf-8")
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    """The command line."""
    parser = argparse.ArgumentParser(prog="finetuning.prompts")
    parser.add_argument("job", choices=JOBS)
    parser.add_argument("--count", type=int, default=BATCH)
    parser.add_argument("--seed", type=int, default=1,
                        help="use a new seed for each round, so the IDs differ")
    parser.add_argument("--batch", type=int, default=BATCH)
    parser.add_argument("--out", type=Path, default=Path("finetuning/out/prompts"))
    args = parser.parse_args(argv)
    for path in write_prompts(args.job, args.count, args.seed, args.out, args.batch):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
