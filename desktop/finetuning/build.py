"""The training file: each accepted training example as chat messages.

Each line holds ``messages`` (the prompt, then the answer to learn) and
``tools``, the tool list that the prompt offered. Only this file goes to the
machine that trains, so that machine needs nothing from the application.

Run from ``desktop/``:

    uv run python -m finetuning.build finetuning/data finetuning/out
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from finetuning import render
from finetuning.examples import check_no_leak, read_folder, validate
from finetuning.review import accepted, decisions

TRAIN_FILE = "train.jsonl"


def build(data_dir: Path, out: Path) -> Counter[str]:
    """Write ``out/train.jsonl`` from the accepted examples of
    ``data_dir/train`` with their edits, and return how many each job has.
    Raises ``ValueError`` if an accepted example has an error, or if a test
    message is also a training message."""
    found = decisions(data_dir / "review.jsonl")
    train = accepted(read_folder(data_dir / "train"), found)
    check_no_leak(train, read_folder(data_dir / "test"))
    lines = []
    for example in train:
        errors = validate(example)
        if errors:
            raise ValueError(f"{example.id}: {'; '.join(errors)}")
        built = render.request(example)
        lines.append(
            json.dumps(
                {
                    "id": example.id,
                    "job": example.job,
                    "messages": built.messages + render.answer(example),
                    "tools": built.tools,
                },
                ensure_ascii=False,
            )
        )
    out.mkdir(parents=True, exist_ok=True)
    (out / TRAIN_FILE).write_text("".join(f"{line}\n" for line in lines), "utf-8")
    return Counter(e.job for e in train)


def main(argv: Sequence[str] | None = None) -> int:
    """The command line."""
    parser = argparse.ArgumentParser(prog="finetuning.build")
    parser.add_argument("data", type=Path, help="the data folder")
    parser.add_argument("out", type=Path, help="the folder for train.jsonl")
    args = parser.parse_args(argv)
    counts = build(args.data, args.out)
    for job, count in sorted(counts.items()):
        print(f"{job}: {count}")
    print(f"{sum(counts.values())} examples in {args.out / TRAIN_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
