"""The examples that train and test the chat model, one JSON object a line.

An example holds the parts of a turn, not the prompt: ``finetuning.render``
builds the prompt from the application's own rules, so a change of wording
needs a new build and no new examples. ``data/train`` and ``data/test`` hold
the files; ``data/review.jsonl`` holds what the reviewer decided.

Run from ``desktop/``:

    uv run python -m finetuning.examples check finetuning/data
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from pathlib import Path

from src.app import config
from src.domain.conversation import rules as conversation_rules
from src.domain.safety import rules as safety_rules
from src.domain.tools import catalog
from src.infrastructure.storage.character_catalog import TomlCharacterCatalog
from src.utils import paths

JOBS = ("voice", "interpretation", "summary", "tools")
MOODS = tuple(conversation_rules.MOOD_LINES)
REASONING_MAX_CHARS = 400
_SCHEMA = conversation_rules.INTERPRETATION_SCHEMA
_CLASSES = tuple(_SCHEMA["properties"]["event_class"]["enum"])  # type: ignore[index]
# What a test example must carry, so the measurement has a right answer.
_EXPECT_KEYS = {
    "voice": {"asks_mood"},
    "interpretation": {"has_fact", "event_class", "crisis"},
    "tools": {"tool"},
    "summary": set(),
}


@dataclass(frozen=True)
class Turn:
    """One earlier message."""

    from_user: bool
    text: str


@dataclass(frozen=True)
class Remembered:
    """A stored line, with the day the user told it."""

    text: str
    told: date


@dataclass(frozen=True)
class ToolUse:
    """One tool call and the data its result is made from. ``data`` stands in
    for what the core thread would read, such as the minutes at the machine."""

    name: str
    arguments: Mapping[str, object] = field(default_factory=dict)
    data: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Example:
    """One turn of one job. Which fields matter depends on ``job``; the others
    keep their empty defaults. ``expect`` holds the right answer of a test
    example."""

    id: str
    job: str
    today: date
    character: str = ""
    history: tuple[Turn, ...] = ()
    message: str = ""
    mood: str | None = None
    remembered: tuple[Remembered, ...] = ()
    stored: tuple[str, ...] = ()
    crisis: bool = False
    known: tuple[str, ...] = ()
    previous: str | None = None
    messages: tuple[Turn, ...] = ()
    calls: tuple[ToolUse, ...] = ()
    reasoning: str = ""
    target: str | dict | None = None
    expect: Mapping[str, object] = field(default_factory=dict)
    tags: tuple[str, ...] = ()


@cache
def characters() -> dict[str, str]:
    """The description of each ready-made character, by its ID."""
    catalog_ = TomlCharacterCatalog(paths.resource("characters.toml"))
    return {t.id: t.description for t in catalog_.templates()}


# ── JSON ────────────────────────────────────────────────────────────────────


def _turns(raw: object) -> tuple[Turn, ...]:
    if not isinstance(raw, list):
        raise ValueError("a list of turns is expected")
    turns = []
    for item in raw:
        side = item["from"]
        if side not in ("user", "companion"):
            raise ValueError(f"'from' is 'user' or 'companion', not {side!r}")
        turns.append(Turn(side == "user", str(item["text"])))
    return tuple(turns)


def from_json(data: Mapping[str, object]) -> Example:
    """The example that ``data`` describes. Raises ``ValueError`` or
    ``KeyError`` for a shape that cannot be read."""
    return Example(
        id=str(data["id"]),
        job=str(data["job"]),
        today=date.fromisoformat(str(data["today"])),
        character=str(data.get("character") or ""),
        history=_turns(data.get("history") or []),
        message=str(data.get("message") or ""),
        mood=data.get("mood"),  # type: ignore[arg-type]
        remembered=tuple(
            Remembered(str(r["text"]), date.fromisoformat(str(r["told"])))
            for r in data.get("remembered") or []  # type: ignore[union-attr]
        ),
        stored=tuple(str(s) for s in data.get("stored") or []),  # type: ignore[union-attr]
        crisis=bool(data.get("crisis", False)),
        known=tuple(str(k) for k in data.get("known") or []),  # type: ignore[union-attr]
        previous=data.get("previous"),  # type: ignore[arg-type]
        messages=_turns(data.get("messages") or []),
        calls=tuple(
            ToolUse(str(c["name"]), dict(c.get("arguments") or {}),
                    dict(c.get("data") or {}))
            for c in data.get("calls") or []  # type: ignore[union-attr]
        ),
        reasoning=str(data.get("reasoning") or ""),
        target=data.get("target"),  # type: ignore[arg-type]
        expect=dict(data.get("expect") or {}),  # type: ignore[arg-type]
        tags=tuple(str(t) for t in data.get("tags") or []),  # type: ignore[union-attr]
    )


def _turns_json(turns: Sequence[Turn]) -> list[dict[str, str]]:
    return [{"from": "user" if t.from_user else "companion", "text": t.text}
            for t in turns]


def to_json(example: Example) -> dict[str, object]:
    """``example`` as a JSON object, with the empty fields left out."""
    data: dict[str, object] = {
        "id": example.id,
        "job": example.job,
        "today": example.today.isoformat(),
        "character": example.character,
        "history": _turns_json(example.history),
        "message": example.message,
        "mood": example.mood,
        "remembered": [{"text": r.text, "told": r.told.isoformat()}
                       for r in example.remembered],
        "stored": list(example.stored),
        "crisis": example.crisis,
        "known": list(example.known),
        "previous": example.previous,
        "messages": _turns_json(example.messages),
        "calls": [{"name": c.name, "arguments": dict(c.arguments),
                   "data": dict(c.data)} for c in example.calls],
        "reasoning": example.reasoning,
        "target": example.target,
        "expect": dict(example.expect),
        "tags": list(example.tags),
    }
    keep = {"id", "job", "today"}
    return {k: v for k, v in data.items() if k in keep or v not in ("", [], {}, None,
                                                                     False)}


def read_examples(path: Path) -> list[Example]:
    """The examples in ``path``; blank lines are skipped. Raises ``ValueError``
    naming the line that cannot be read."""
    examples = []
    for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            examples.append(from_json(json.loads(line)))
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f"{path.name} line {number}: {error}") from error
    return examples


def write_examples(path: Path, examples: Iterable[Example]) -> None:
    """Write ``examples`` to ``path``, one a line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(to_json(e), ensure_ascii=False) for e in examples]
    path.write_text("".join(f"{line}\n" for line in lines), "utf-8")


def read_folder(folder: Path) -> list[Example]:
    """The examples of every ``.jsonl`` file in ``folder``, in name order."""
    if not folder.is_dir():
        return []
    return [e for path in sorted(folder.glob("*.jsonl")) for e in read_examples(path)]


# ── checks ──────────────────────────────────────────────────────────────────


def _turn_errors(
    turns: Sequence[Turn], name: str, ends_with_companion: bool
) -> list[str]:
    errors = []
    if turns and not turns[0].from_user:
        errors.append(f"{name} must start with the user")
    for a, b in zip(turns, turns[1:]):
        if a.from_user == b.from_user:
            errors.append(f"{name} has two messages in a row from one side")
            break
    if ends_with_companion and turns and turns[-1].from_user:
        errors.append(f"{name} must end with the companion, before the message")
    if any(not t.text.strip() for t in turns):
        errors.append(f"{name} has an empty message")
    return errors


def _interpretation_errors(target: object) -> list[str]:
    if not isinstance(target, dict):
        return ["target is not a JSON object"]
    errors = []
    missing = set(_SCHEMA["required"]) - set(target)  # type: ignore[arg-type]
    if missing:
        errors.append(f"target lacks {', '.join(sorted(missing))}")
    extra = set(target) - set(_SCHEMA["properties"])  # type: ignore[arg-type]
    if extra:
        errors.append(f"target has unknown fields {', '.join(sorted(extra))}")
    facts = target.get("facts")
    if "facts" in target and (
        not isinstance(facts, list) or not all(isinstance(f, str) for f in facts)
    ):
        errors.append("facts is not a list of text")
    importance = target.get("importance")
    if "importance" in target and (
        isinstance(importance, bool)
        or not isinstance(importance, int)
        or not 1 <= importance <= 10
    ):
        errors.append("importance is not a whole number from 1 to 10")
    if "crisis" in target and not isinstance(target.get("crisis"), bool):
        errors.append("crisis is not true or false")
    if "event_class" in target and target.get("event_class") not in _CLASSES:
        errors.append(f"event_class is not one of {', '.join(_CLASSES)}")
    confidence = target.get("confidence")
    if "confidence" in target and (
        isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not 0 <= confidence <= 1
    ):
        errors.append("confidence is not a number from 0 to 1")
    style = target.get("style_request")
    if style is not None and not isinstance(style, str):
        errors.append("style_request is not text or null")
    return errors


def _call_errors(calls: Sequence[ToolUse]) -> list[str]:
    errors = []
    if len(calls) > catalog.TOOL_ROUNDS:
        errors.append(f"more than {catalog.TOOL_ROUNDS} tool calls")
    for call in calls:
        spec = catalog.spec(call.name)
        if spec is None:
            errors.append(f"no tool is called {call.name!r}")
            continue
        required = spec.parameters.get("required", [])
        lacking = [name for name in required if name not in call.arguments]  # type: ignore[union-attr]
        if lacking:
            errors.append(f"{call.name} lacks {', '.join(lacking)}")
    return errors


def validate(example: Example, *, test: bool = False) -> list[str]:
    """What is wrong with ``example``; empty if nothing. A test example needs
    ``expect`` and may leave out the target of a voice turn."""
    if example.job not in JOBS:
        return [f"job is not one of {', '.join(JOBS)}"]
    errors = []
    if not example.id.strip():
        errors.append("id is empty")
    if len(example.reasoning) > REASONING_MAX_CHARS:
        errors.append(f"reasoning is longer than {REASONING_MAX_CHARS} characters")
    job = example.job
    if job != "summary":
        if example.character not in characters():
            errors.append(f"no character has the id {example.character!r}")
        if not example.message.strip():
            errors.append("message is empty")
        if len(example.message) > config.MESSAGE_MAX_CHARS:
            errors.append(f"message is longer than {config.MESSAGE_MAX_CHARS}")
        errors += _turn_errors(example.history, "history", ends_with_companion=True)
    if example.mood is not None and example.mood not in MOODS:
        errors.append(f"mood is not one of {', '.join(MOODS)}")
    if example.crisis and example.mood is not None:
        errors.append("a crisis turn has no mood")
    target = example.target
    if job == "interpretation":
        errors += _interpretation_errors(target)
    elif target is not None and not isinstance(target, str):
        errors.append("target is not text")
    elif not (target or "").strip() and not (test and job == "voice"):
        errors.append("target is empty")
    if job == "voice" and example.crisis and isinstance(target, str) and target:
        if not safety_rules.reply_complies(target):
            errors.append("a crisis reply must say it is a fictional character "
                          "that cannot take the place of a real person")
    if job == "summary":
        if not example.messages:
            errors.append("messages is empty")
        limit = conversation_rules.SUMMARY_MAX_CHARS
        if isinstance(target, str) and len(target) > limit:
            errors.append("the summary is too long")
    if job == "tools":
        errors += _call_errors(example.calls)
    if test:
        lacking = _EXPECT_KEYS[job] - set(example.expect)
        if lacking:
            errors.append(f"expect lacks {', '.join(sorted(lacking))}")
    return errors


def coverage(examples: Iterable[Example]) -> Counter[str]:
    """How many examples each job, character, mood and tag has."""
    counts: Counter[str] = Counter()
    for e in examples:
        counts[e.job] += 1
        if e.character:
            counts[f"{e.job}/character/{e.character}"] += 1
        if e.mood:
            counts[f"{e.job}/mood/{e.mood}"] += 1
        for tag in e.tags:
            counts[f"{e.job}/tag/{tag}"] += 1
    return counts


def duplicate_ids(examples: Iterable[Example]) -> list[str]:
    """Each ID that more than one example has."""
    counts = Counter(e.id for e in examples)
    return sorted(i for i, n in counts.items() if n > 1)


def check_no_leak(train: Iterable[Example], test: Iterable[Example]) -> None:
    """Raise ``ValueError`` if a message of a test example is also a message of
    a training example, apart from case and spacing."""

    def key(text: str) -> str:
        return " ".join(text.casefold().split())

    seen = {key(e.message) for e in train if e.message}
    leaked = sorted(e.id for e in test if e.message and key(e.message) in seen)
    if leaked:
        raise ValueError(f"Test messages also in training: {', '.join(leaked)}")


# ── command line ────────────────────────────────────────────────────────────


def check(data_dir: Path) -> int:
    """Print the errors, the coverage and the warnings of every example under
    ``data_dir``. Returns the number of examples with an error."""
    from finetuning import checks  # the checks read examples too

    parts = {
        "seeds": read_folder(data_dir / "seeds"),
        "train": read_folder(data_dir / "train"),
        "test": read_folder(data_dir / "test"),
    }
    every = [e for examples in parts.values() for e in examples]
    failed = 0
    for twice in duplicate_ids(every):
        print(f"ERROR {twice}: the ID is used more than once")
        failed += 1
    for part, examples in parts.items():
        for e in examples:
            errors = validate(e, test=part == "test")
            if errors:
                failed += 1
                print(f"ERROR {part}/{e.id}: {'; '.join(errors)}")
    try:
        check_no_leak(parts["train"] + parts["seeds"], parts["test"])
    except ValueError as error:
        print(f"ERROR {error}")
        failed += 1
    warned: Counter[str] = Counter()
    for e in every:
        warned.update(checks.warnings(e))
    for part, examples in parts.items():
        print(f"\n{part}: {len(examples)} examples")
        for key, count in sorted(coverage(examples).items()):
            print(f"  {key}: {count}")
    print("\nwarnings:" if warned else "\nwarnings: none")
    for name, count in warned.most_common():
        print(f"  {name}: {count}")
    return failed


def main(argv: Sequence[str] | None = None) -> int:
    """The command line. Returns 1 if an example has an error."""
    parser = argparse.ArgumentParser(prog="finetuning.examples")
    commands = parser.add_subparsers(dest="command", required=True)
    checked = commands.add_parser("check", help="check every example")
    checked.add_argument("data", type=Path, help="the data folder")
    args = parser.parse_args(argv)
    return 1 if check(args.data) else 0


if __name__ == "__main__":
    raise SystemExit(main())
