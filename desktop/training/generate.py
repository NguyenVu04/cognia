"""The training examples: their shape, their checks, and their review.

Nothing here calls a model. The author selects the generating model, and its
terms must allow the use of its output for training (ARCHITECTURE.md, section 12).

Run from ``desktop/``:

    uv run --project training python -m training.generate validate FILE
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from src.domain.conversation.models.message import COMPANION, USER

JOBS = ("voice", "interpretation")

EVENT_CLASSES = (
    "praise",
    "complaint",
    "good_news",
    "bad_news",
    "shared_worry",
    "nothing",
)

_INTERPRETATION_FIELDS = {
    "event_class",
    "confidence",
    "importance",
    "crisis",
    "facts",
    "commitments",
    "closes_commitment",
    "style_request",
}
# The tags are the tokenizer's job: reasoning has its own field (section 6.11).
_THINK_TAGS = ("[THINK]", "[/THINK]")


@dataclass(frozen=True)
class Turn:
    """One line of the history. ``role`` is USER or COMPANION."""

    role: str
    text: str


@dataclass(frozen=True)
class Example:
    """One training item (section 6.16). ``job`` is one of :data:`JOBS`.

    ``mood``, ``remembered`` and ``instruction`` are layer 4, and ``cell`` is
    the place of the example in the grid.
    """

    job: str
    character: str
    turns: tuple[Turn, ...]
    reasoning: str
    target: str
    cell: str
    mood: str = ""
    remembered: tuple[str, ...] = ()
    instruction: str = ""
    reviewed: bool = False


def make_cells(
    characters: Sequence[str],
    situations: Sequence[str],
    classes: Sequence[str],
    lengths: Sequence[str],
) -> list[str]:
    """Every combination, as ``character/situation/class/length``."""
    product = itertools.product(characters, situations, classes, lengths)
    return ["/".join(parts) for parts in product]


def _interpretation_errors(target: str) -> list[str]:
    try:
        answer = json.loads(target)
    except ValueError:
        return ["target is not JSON"]
    if not isinstance(answer, dict):
        return ["target is not a JSON object"]
    errors = []
    if missing := _INTERPRETATION_FIELDS - answer.keys():
        errors.append(f"target has no {', '.join(sorted(missing))}")
    if "event_class" in answer and answer["event_class"] not in EVENT_CLASSES:
        errors.append(f"unknown event class {answer['event_class']!r}")
    importance = answer.get("importance", 1)
    if isinstance(importance, bool) or not isinstance(importance, int):
        errors.append("importance is not a whole number")
    elif not 1 <= importance <= 10:  # docs/ERD.md
        errors.append("importance is outside 1 to 10")
    confidence = answer.get("confidence", 0)
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        errors.append("confidence is not a number")
    elif not 0 <= confidence <= 1:
        errors.append("confidence is outside 0 to 1")
    if "crisis" in answer and not isinstance(answer["crisis"], bool):
        errors.append("crisis is not true or false")
    return errors


def validate(example: Example) -> list[str]:
    """Each thing wrong with ``example``, in words. Empty if nothing is wrong."""
    errors = []
    if example.job not in JOBS:
        errors.append(f"unknown job {example.job!r}")
    if not example.character.strip():
        errors.append("character is empty")
    if not example.reasoning.strip():
        errors.append("reasoning is empty")
    if not example.target.strip():
        errors.append("target is empty")
    if not example.cell.strip():
        errors.append("cell is empty")
    if not example.turns:
        errors.append("turns is empty")
    elif example.turns[-1].role != USER:
        errors.append("the last turn is not from the user")
    if any(turn.role not in (USER, COMPANION) for turn in example.turns):
        errors.append("a turn has an unknown role")
    if any(tag in example.target + example.reasoning for tag in _THINK_TAGS):
        errors.append("target or reasoning holds a think tag")
    if example.job == "interpretation":
        errors.extend(_interpretation_errors(example.target))
    return errors


def _from_json(line: str) -> Example:
    data = json.loads(line)
    return Example(
        **{
            **data,
            "turns": tuple(Turn(**turn) for turn in data["turns"]),
            "remembered": tuple(data.get("remembered", ())),
        }
    )


def read_examples(path: Path) -> list[Example]:
    """The examples of a JSONL file. Raises ``ValueError`` naming the bad line."""
    examples = []
    for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            examples.append(_from_json(line))
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError(f"{path}, line {number}: {error}") from error
    return examples


def write_examples(path: Path, examples: Iterable[Example]) -> None:
    """Write ``examples`` as JSONL, in place of what ``path`` held."""
    lines = (json.dumps(asdict(example), ensure_ascii=False) for example in examples)
    path.write_text("".join(f"{line}\n" for line in lines), "utf-8")


def coverage(examples: Iterable[Example]) -> Counter[str]:
    """How many examples each grid cell holds."""
    return Counter(example.cell for example in examples)


def split(
    examples: Sequence[Example], val_share: float, seed: int
) -> tuple[list[Example], list[Example]]:
    """Train and validation sets that share no character, so the validation set
    measures characters that training did not see (section 6.11.3). Raises
    ``ValueError`` if there are fewer than two characters."""
    characters = sorted({example.character for example in examples})
    if len(characters) < 2:
        raise ValueError("A split needs at least two characters.")
    random.Random(seed).shuffle(characters)
    size = min(max(1, round(len(characters) * val_share)), len(characters) - 1)
    held_out = set(characters[:size])
    train = [example for example in examples if example.character not in held_out]
    val = [example for example in examples if example.character in held_out]
    return train, val


def _user_lines(examples: Iterable[Example]) -> set[str]:
    return {
        turn.text
        for example in examples
        for turn in example.turns
        if turn.role == USER
    }


def check_no_leak(train: Iterable[Example], test: Iterable[Example]) -> None:
    """Raise ``ValueError`` if a test character or user message is in the training
    set (section 8.6: training never reads the test sets)."""
    train, test = list(train), list(test)
    shared = {e.character for e in train} & {e.character for e in test}
    if shared:
        raise ValueError(f"Shared characters: {sorted(shared)}")
    if shared := _user_lines(train) & _user_lines(test):
        raise ValueError(f"Shared user messages: {sorted(shared)}")


def _key(example: Example) -> str:
    content = asdict(replace(example, reviewed=False))
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def _show(example: Example) -> str:
    history = "\n".join(f"  {turn.role}: {turn.text}" for turn in example.turns)
    return (
        f"\n[{example.job}] {example.cell}\n"
        f"character: {example.character}\n{history}\n"
        f"mood: {example.mood}\nremembered: {list(example.remembered)}\n"
        f"instruction: {example.instruction}\n"
        f"reasoning: {example.reasoning}\ntarget: {example.target}\n"
    )


def review(
    source: Path, destination: Path, read: Callable[[str], str] = input
) -> int:
    """Ask about each example of ``source`` and return how many were accepted now.

    ``a`` accepts, ``r`` rejects, and ``q`` stops. An accepted example goes to
    ``destination`` at once, and a rejected one goes to ``<destination>.rejected``.
    A later run skips each example that has an answer, so a stop loses nothing.
    """
    rejected = destination.with_suffix(destination.suffix + ".rejected")
    answered = {
        _key(example)
        for path in (destination, rejected)
        if path.exists()
        for example in read_examples(path)
    }
    accepted = 0
    for example in read_examples(source):
        if _key(example) in answered:
            continue
        print(_show(example))
        answer = ""
        while answer not in ("a", "r", "q"):
            answer = read("[a]ccept, [r]eject, [q]uit: ").strip().lower()
        if answer == "q":
            break
        kept = replace(example, reviewed=answer == "a")
        target = destination if answer == "a" else rejected
        with target.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(kept), ensure_ascii=False) + "\n")
        accepted += answer == "a"
    return accepted


def _validate_file(path: Path) -> int:
    try:
        examples = read_examples(path)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    problems = 0
    for number, example in enumerate(examples, start=1):
        for error in validate(example):
            print(f"example {number}: {error}", file=sys.stderr)
            problems += 1
    print(f"{len(examples)} examples, {problems} problems")
    return 1 if problems else 0


def _lines(path: str) -> list[str]:
    return Path(path).read_text("utf-8").split()


def main(argv: Sequence[str] | None = None) -> int:
    """The command line. Returns the exit code."""
    parser = argparse.ArgumentParser(prog="training.generate")
    commands = parser.add_subparsers(dest="command", required=True)

    cells = commands.add_parser("cells", help="print the grid")
    for name in ("characters", "situations", "lengths"):
        cells.add_argument(name, help="a file of names, split by white space")

    for name, text in (("validate", "check a file"), ("coverage", "count each cell")):
        commands.add_parser(name, help=text).add_argument("file", type=Path)

    reviewing = commands.add_parser("review", help="review a file")
    reviewing.add_argument("source", type=Path)
    reviewing.add_argument("destination", type=Path)

    leak = commands.add_parser("leak", help="compare train and test files")
    leak.add_argument("train", type=Path)
    leak.add_argument("test", type=Path)

    args = parser.parse_args(argv)
    if args.command == "cells":
        grid = make_cells(
            _lines(args.characters),
            _lines(args.situations),
            EVENT_CLASSES,
            _lines(args.lengths),
        )
        print("\n".join(grid))
    elif args.command == "validate":
        return _validate_file(args.file)
    elif args.command == "coverage":
        for cell, count in sorted(coverage(read_examples(args.file)).items()):
            print(f"{count}\t{cell}")
    elif args.command == "review":
        print(f"{review(args.source, args.destination)} accepted")
    elif args.command == "leak":
        try:
            check_no_leak(read_examples(args.train), read_examples(args.test))
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
