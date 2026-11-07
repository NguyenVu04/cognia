"""LoRA training on the built training file, on a machine with a CUDA GPU.

The file comes from ``finetuning.build``: each line holds the chat messages and
the tool list, so this module needs nothing from the application. The loss
counts the model's answers only, not the prompt.

Run from ``desktop/``:

    uv run --project finetuning --extra gpu python -m finetuning.train \\
        finetuning/out/train.jsonl finetuning/out/adapter
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

BASE_MODEL = "mistralai/Ministral-3-3B-Reasoning-2512"


@dataclass(frozen=True)
class TrainConfig:
    """One training run. The two parts mark where a user turn and an answer
    begin in the chat template; check them against the template before the
    first real run."""

    base: str = BASE_MODEL
    rank: int = 16
    alpha: int = 16
    learning_rate: float = 2e-4
    batch_size: int = 1
    accumulation: int = 4
    # Twelve tool schemas, the system text and a history fill about 2 500
    # tokens.
    max_seq_length: int = 4096
    epochs: int = 2
    fraction: float = 1.0
    seed: int = 3407
    load_in_4bit: bool = True
    instruction_part: str = "[INST]"
    response_part: str = "[/INST]"


def read_rows(path: Path) -> list[dict]:
    """The lines of a training file. Raises ``ValueError`` for an empty file or
    a line without ``messages``."""
    rows = []
    for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row.get("messages"), list) or not row["messages"]:
            raise ValueError(f"Line {number} has no messages.")
        rows.append(row)
    if not rows:
        raise ValueError(f"{path} holds no examples. Run finetuning.build first.")
    return rows


def split(rows: Sequence[dict], val_share: float, seed: int) -> tuple[list, list]:
    """A training part and a validation part, the same for one seed. The
    validation part has at least one row when there are two or more."""
    if not 0 <= val_share < 1:
        raise ValueError("The validation share must be at least 0 and below 1.")
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    size = round(len(shuffled) * val_share)
    if val_share and len(shuffled) > 1:
        size = max(size, 1)
    return shuffled[size:], shuffled[:size]


def take_fraction(rows: Sequence[dict], fraction: float, seed: int) -> list[dict]:
    """A share of ``rows`` for a learning curve. For one seed, a smaller share
    is part of a larger one. Raises ``ValueError`` outside (0, 1]."""
    if not 0 < fraction <= 1:
        raise ValueError("The fraction must be above 0, and at most 1.")
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    return shuffled[: round(len(shuffled) * fraction)]


def chat_texts(rows: Sequence[dict], render: Callable[[dict], str]) -> list[str]:
    """The training text of each row, from ``render``. Raises ``ValueError``
    for a row whose text lost the reasoning of one of its answers."""
    texts = []
    for row in rows:
        text = render(row)
        for message in row["messages"]:
            reasoning = message.get("reasoning_content")
            if reasoning and f"[THINK]{reasoning}[/THINK]" not in text:
                raise ValueError(
                    f"Row {row.get('id')} lost its reasoning in the chat template."
                )
        texts.append(text)
    return texts


def train_lora(
    config: TrainConfig, train: Sequence[dict], val: Sequence[dict], output: Path
) -> Path:
    """Train an adapter on the language layers, save it in ``output``, and
    return ``output``. Needs the ``gpu`` extra and a GPU."""
    # Imported here so that the tests and the other tools need no torch.
    from unsloth import FastModel  # isort: skip
    from datasets import Dataset
    from transformers import AutoTokenizer
    from trl import SFTConfig, SFTTrainer
    from unsloth.chat_templates import train_on_responses_only

    model, tokenizer = FastModel.from_pretrained(
        model_name=config.base,
        max_seq_length=config.max_seq_length,
        load_in_4bit=config.load_in_4bit,
    )
    # The 4-bit copy that Unsloth loads has a template that drops the
    # reasoning; the base model's template matches what llama.cpp renders.
    tokenizer.chat_template = AutoTokenizer.from_pretrained(config.base).chat_template
    model = FastModel.get_peft_model(
        model,
        r=config.rank,
        lora_alpha=config.alpha,
        finetune_vision_layers=False,  # Cognia sends text only
        finetune_language_layers=True,
        random_state=config.seed,
    )

    def dataset(rows: Sequence[dict]) -> Dataset:
        texts = chat_texts(
            rows,
            lambda row: tokenizer.apply_chat_template(
                row["messages"],
                tools=row.get("tools") or None,
                tokenize=False,
                add_generation_prompt=False,
            ),
        )
        # The trainer adds the first token again.
        bos = tokenizer.bos_token or ""
        return Dataset.from_list([{"text": text.removeprefix(bos)} for text in texts])

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset(train),
        eval_dataset=dataset(val) if val else None,
        args=SFTConfig(
            output_dir=str(output),
            dataset_text_field="text",
            max_seq_length=config.max_seq_length,
            per_device_train_batch_size=config.batch_size,
            gradient_accumulation_steps=config.accumulation,
            num_train_epochs=config.epochs,
            learning_rate=config.learning_rate,
            optim="adamw_8bit",
            eval_strategy="epoch" if val else "no",
            seed=config.seed,
            report_to="none",
        ),
    )
    trainer = train_on_responses_only(
        trainer,
        instruction_part=config.instruction_part,
        response_part=config.response_part,
    )
    trainer.train()
    model.save_pretrained(str(output))
    tokenizer.save_pretrained(str(output))
    return output


def main(argv: Sequence[str] | None = None) -> int:
    """The command line. Returns the exit code."""
    parser = argparse.ArgumentParser(prog="finetuning.train")
    parser.add_argument("rows", type=Path, help="the train.jsonl of finetuning.build")
    parser.add_argument("output", type=Path, help="the folder for the adapter")
    parser.add_argument("--base", default=BASE_MODEL)
    parser.add_argument("--epochs", type=int, default=TrainConfig.epochs)
    parser.add_argument("--rank", type=int, default=TrainConfig.rank)
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--val-share", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=TrainConfig.seed)
    parser.add_argument("--instruction-part", default=TrainConfig.instruction_part)
    parser.add_argument("--response-part", default=TrainConfig.response_part)
    args = parser.parse_args(argv)

    config = replace(
        TrainConfig(),
        base=args.base,
        epochs=args.epochs,
        rank=args.rank,
        alpha=args.rank,
        fraction=args.fraction,
        seed=args.seed,
        instruction_part=args.instruction_part,
        response_part=args.response_part,
    )
    train, val = split(read_rows(args.rows), args.val_share, config.seed)
    used = take_fraction(train, config.fraction, config.seed)
    print(f"{len(used)} training rows, {len(val)} validation rows")
    print(f"Adapter: {train_lora(config, used, val, args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
