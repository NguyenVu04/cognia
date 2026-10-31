"""Measure a model and apply the acceptance gate (ARCHITECTURE.md, section 8.6).

``LlamaClient`` and ``reply_complies`` do not exist yet. So a caller passes the
call to the model and the safety check in, and this module holds no HTTP code
(section 6.2, rule 10). ``check_wording`` also waits for ``domain/speech``.

Run from ``desktop/``:

    uv run --project training python -m training.evaluate gate TUNED BASE LIMITS REPORT
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean

RUBRIC_CRITERIA = ("fits_character", "natural", "stays_in_scope")
_RUBRIC_SCORES = range(1, 6)


@dataclass(frozen=True)
class Reply:
    """What the model wrote, and how long the first word took."""

    text: str
    first_word_seconds: float


#: Takes the messages and an optional JSON schema, and calls ``llama-server``.
Generate = Callable[[list[dict[str, str]], dict | None], Reply]


@dataclass(frozen=True)
class Labelled:
    """The right answer for one message of the interpretation set."""

    event_class: str
    importance: int
    crisis: bool


@dataclass(frozen=True)
class Report:
    """The measurements of one GGUF file."""

    class_accuracy: float
    crisis_recall: float
    importance_error: float
    complies_share: float
    rubric_mean: float
    first_word_p95: float
    file_bytes: int


@dataclass(frozen=True)
class Thresholds:
    """The limits that the author sets before training (section 12, item 20).
    ``rubric_margin`` is how far the tuned rubric mean must exceed the base."""

    class_accuracy: float
    crisis_recall: float
    complies_share: float
    rubric_margin: float
    first_word_p95: float
    file_bytes: int


@dataclass(frozen=True)
class Gate:
    """The result of one check."""

    name: str
    passed: bool
    detail: str


def collect(
    generate: Generate,
    prompts: Sequence[list[dict[str, str]]],
    schema: dict | None = None,
) -> list[Reply]:
    """One reply for each prompt."""
    return [generate(prompt, schema) for prompt in prompts]


def score_interpretation(
    answers: Sequence[Mapping], labels: Sequence[Labelled]
) -> dict[str, float]:
    """``class_accuracy``, ``crisis_recall`` and ``importance_error``, which is the
    mean absolute error. Raises ``ValueError`` if the lengths differ, or if no
    label is a crisis, because the recall then has no meaning."""
    if len(answers) != len(labels) or not labels:
        raise ValueError("Answers and labels must match, and must not be empty.")
    crises = [a for a, label in zip(answers, labels) if label.crisis]
    if not crises:
        raise ValueError("The set holds no crisis message.")
    return {
        "class_accuracy": fmean(
            a["event_class"] == label.event_class for a, label in zip(answers, labels)
        ),
        "crisis_recall": fmean(bool(answer["crisis"]) for answer in crises),
        "importance_error": fmean(
            abs(a["importance"] - label.importance)
            for a, label in zip(answers, labels)
        ),
    }


def share_complying(replies: Sequence[str], complies: Callable[[str], bool]) -> float:
    """The share of ``replies`` that ``complies`` accepts, with no added line.
    Raises ``ValueError`` if ``replies`` is empty."""
    if not replies:
        raise ValueError("There are no replies to check.")
    return fmean(bool(complies(reply)) for reply in replies)


def percentile(values: Sequence[float], share: float) -> float:
    """The nearest-rank percentile. ``share`` is above 0 and at most 1."""
    if not values or not 0 < share <= 1:
        raise ValueError("Needs values, and a share above 0 and at most 1.")
    return sorted(values)[math.ceil(share * len(values)) - 1]


def _key_path(path: Path) -> Path:
    return path.with_suffix(".key.csv")


def write_rubric_sheet(
    samples: Mapping[str, Sequence[str]], path: Path, seed: int
) -> Path:
    """Write a blind sheet to ``path`` from replies by model name, and return it.

    The rows are in random order and hold no model name. The names go to a
    separate ``.key.csv`` file, so the person who scores does not open that file.
    """
    rows = [(model, text) for model, texts in samples.items() for text in texts]
    random.Random(seed).shuffle(rows)
    with path.open("w", newline="", encoding="utf-8") as sheet:
        writer = csv.writer(sheet)
        writer.writerow(("id", "text", *RUBRIC_CRITERIA))
        writer.writerows((i, text, "", "", "") for i, (_, text) in enumerate(rows))
    with _key_path(path).open("w", newline="", encoding="utf-8") as key:
        writer = csv.writer(key)
        writer.writerow(("id", "model"))
        writer.writerows((i, model) for i, (model, _) in enumerate(rows))
    return path


def read_rubric_sheet(path: Path) -> dict[str, float]:
    """The mean score of each model, from a scored sheet and its key. Raises
    ``ValueError`` on a blank score, or on a score outside 1 to 5."""
    with _key_path(path).open(newline="", encoding="utf-8") as key:
        models = {row["id"]: row["model"] for row in csv.DictReader(key)}
    scores: dict[str, list[int]] = {}
    with path.open(newline="", encoding="utf-8") as sheet:
        for row in csv.DictReader(sheet):
            for criterion in RUBRIC_CRITERIA:
                score = row[criterion].strip()
                if not score.isdigit() or int(score) not in _RUBRIC_SCORES:
                    raise ValueError(f"Row {row['id']}, {criterion}: {score!r}.")
                scores.setdefault(models[row["id"]], []).append(int(score))
    return {model: fmean(values) for model, values in scores.items()}


def gates(
    tuned: Report, base: Report, thresholds: Thresholds
) -> tuple[Gate, ...]:
    """The four checks of section 8.6. Each stands alone, because one set of
    weights does both jobs and a gain in one job can harm the other (D-27)."""
    voice_gain = tuned.rubric_mean - base.rubric_mean
    return (
        Gate(
            "voice",
            voice_gain > thresholds.rubric_margin,
            f"rubric {tuned.rubric_mean:.2f}, base {base.rubric_mean:.2f}",
        ),
        Gate(
            "interpretation",
            tuned.class_accuracy >= max(thresholds.class_accuracy, base.class_accuracy)
            and tuned.crisis_recall
            >= max(thresholds.crisis_recall, base.crisis_recall),
            f"accuracy {tuned.class_accuracy:.3f}, "
            f"crisis recall {tuned.crisis_recall:.3f}",
        ),
        Gate(
            "safety",
            tuned.complies_share
            >= max(thresholds.complies_share, base.complies_share),
            f"complies {tuned.complies_share:.3f}",
        ),
        Gate(
            "cost",
            tuned.first_word_p95 <= thresholds.first_word_p95
            and tuned.file_bytes <= thresholds.file_bytes,
            f"first word {tuned.first_word_p95:.2f} s, {tuned.file_bytes} bytes",
        ),
    )


def accepted(tuned: Report, base: Report, thresholds: Thresholds) -> bool:
    """True if the tuned model passes every gate."""
    return all(gate.passed for gate in gates(tuned, base, thresholds))


def write_report(
    path: Path, gates_: Sequence[Gate], tuned: Report, base: Report
) -> None:
    """Write the measurement report as Markdown."""
    lines = ["# Measurement report", "", "| Gate | Result | Detail |", "|---|---|---|"]
    lines += [
        f"| {gate.name} | {'pass' if gate.passed else 'FAIL'} | {gate.detail} |"
        for gate in gates_
    ]
    lines += ["", "| Measure | Tuned | Base |", "|---|---|---|"]
    tuned_values, base_values = asdict(tuned), asdict(base)
    lines += [
        f"| {name} | {value} | {base_values[name]} |"
        for name, value in tuned_values.items()
    ]
    path.write_text("\n".join(lines) + "\n", "utf-8")


def _load(kind: type, path: Path):
    return kind(**json.loads(path.read_text("utf-8")))


def main(argv: Sequence[str] | None = None) -> int:
    """The command line. Returns the exit code, which is 1 for a refused model."""
    parser = argparse.ArgumentParser(prog="training.evaluate")
    commands = parser.add_subparsers(dest="command", required=True)

    sheet = commands.add_parser("rubric", help="write a blind sheet")
    sheet.add_argument("samples", type=Path, help="JSON: model name to replies")
    sheet.add_argument("sheet", type=Path)
    sheet.add_argument("--seed", type=int, default=1)

    score = commands.add_parser("score", help="read a scored sheet")
    score.add_argument("sheet", type=Path)

    gate = commands.add_parser("gate", help="apply the acceptance gate")
    gate.add_argument("tuned", type=Path, help="JSON: a Report")
    gate.add_argument("base", type=Path, help="JSON: a Report")
    gate.add_argument("thresholds", type=Path, help="JSON: Thresholds")
    gate.add_argument("report", type=Path, help="the Markdown file to write")

    args = parser.parse_args(argv)
    if args.command == "rubric":
        samples = json.loads(args.samples.read_text("utf-8"))
        print(write_rubric_sheet(samples, args.sheet, args.seed))
    elif args.command == "score":
        print(json.dumps(read_rubric_sheet(args.sheet), indent=2))
    else:
        tuned, base = _load(Report, args.tuned), _load(Report, args.base)
        limits = _load(Thresholds, args.thresholds)
        results = gates(tuned, base, limits)
        write_report(args.report, results, tuned, base)
        for result in results:
            print(result.name, "pass" if result.passed else "FAIL", result.detail)
        return 0 if accepted(tuned, base, limits) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
