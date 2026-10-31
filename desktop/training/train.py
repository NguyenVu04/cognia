"""LoRA training on the reviewed examples (ARCHITECTURE.md, section 8.6).

Run from ``desktop/``, on a machine with a GPU:

    uv run --project training --extra gpu python -m training.train EXAMPLES OUTPUT
"""

from __future__ import annotations

import argparse
import random
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from src.domain.conversation import rules
from src.domain.conversation.models.message import USER
from training.generate import Example, read_examples, split, validate

BASE_MODEL = "mistralai/Ministral-3-3B-Reasoning-2512"

# The chat template adds its own reasoning prompt only if no system message exists,
# and this project always sends one. The run-time client must send the same text.
REASONING_RULE = (
    "First think inside [THINK] and [/THINK]. The user never sees this. "
    "Then write your reply."
)


@dataclass(frozen=True)
class TrainConfig:
    """One training run. The defaults start from the Unsloth text example."""

    base: str = BASE_MODEL
    rank: int = 8
    alpha: int = 8
    learning_rate: float = 2e-4
    batch_size: int = 1
    accumulation: int = 4
    max_seq_length: int = 2048
    epochs: int = 3
    fraction: float = 1.0
    seed: int = 3407
    load_in_4bit: bool = True


def load_reviewed(path: Path) -> list[Example]:
    """The examples of ``path``. Raises ``ValueError`` on an item that has not
    been reviewed or that fails :func:`~training.generate.validate` (section 6.16)."""
    examples = read_examples(path)
    for number, example in enumerate(examples, start=1):
        if not example.reviewed:
            raise ValueError(f"Example {number} has not been reviewed.")
        if errors := validate(example):
            raise ValueError(f"Example {number}: {'; '.join(errors)}")
    return examples


def take_fraction(
    examples: Sequence[Example], fraction: float, seed: int
) -> list[Example]:
    """A share of ``examples`` for the learning curve. For one seed, a smaller
    share is part of a larger one. Raises ``ValueError`` outside (0, 1]."""
    if not 0 < fraction <= 1:
        raise ValueError("The fraction must be above 0, and at most 1.")
    shuffled = list(examples)
    random.Random(seed).shuffle(shuffled)
    return shuffled[: round(len(shuffled) * fraction)]


def to_messages(example: Example) -> list[dict[str, str]]:
    """The chat messages of ``example``, with the layers in run-time order.

    Layer 4 goes at the end of the last user turn, because it follows the history
    (section 6.11.2). Only the answer holds reasoning, because a run-time history
    holds none. The run-time client must build its messages the same way.
    """
    system = f"{rules.system_text(example.character)}\n\n{REASONING_RULE}"
    messages = [{"role": "system", "content": system}]
    messages += [
        {"role": "user" if turn.role == USER else "assistant", "content": turn.text}
        for turn in example.turns
    ]
    layer_4 = rules.turn_text(example.mood, example.remembered, example.instruction)
    if layer_4:
        messages[-1]["content"] += f"\n\n{layer_4}"
    messages.append(
        {
            "role": "assistant",
            "content": example.target,
            "reasoning_content": example.reasoning,
        }
    )
    return messages


def train_lora(
    config: TrainConfig,
    train: Sequence[Example],
    val: Sequence[Example],
    output: Path,
) -> Path:
    """Train an adapter on the language layers, save it in ``output``, and return
    ``output``. Needs the ``gpu`` extra and a GPU."""
    # Imported here so that the tests and the other tools need no torch.
    from unsloth import FastModel  # isort: skip
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer

    model, tokenizer = FastModel.from_pretrained(
        model_name=config.base,
        max_seq_length=config.max_seq_length,
        load_in_4bit=config.load_in_4bit,
    )
    model = FastModel.get_peft_model(
        model,
        r=config.rank,
        lora_alpha=config.alpha,
        finetune_vision_layers=False,  # Cognia sends text only
        finetune_language_layers=True,
        random_state=config.seed,
    )

    def dataset(examples: Sequence[Example]) -> Dataset:
        texts = [
            tokenizer.apply_chat_template(
                to_messages(example), tokenize=False, add_generation_prompt=False
            )
            for example in examples
        ]
        # The trainer adds the first token again.
        bos = tokenizer.bos_token or ""
        return Dataset.from_list([{"text": text.removeprefix(bos)} for text in texts])

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset(train),
        eval_dataset=dataset(val),
        args=SFTConfig(
            output_dir=str(output),
            dataset_text_field="text",
            per_device_train_batch_size=config.batch_size,
            gradient_accumulation_steps=config.accumulation,
            num_train_epochs=config.epochs,
            learning_rate=config.learning_rate,
            optim="adamw_8bit",
            eval_strategy="epoch",
            seed=config.seed,
            report_to="none",
        ),
    )
    trainer.train()
    model.save_pretrained(str(output))
    tokenizer.save_pretrained(str(output))
    return output


def main(argv: Sequence[str] | None = None) -> int:
    """The command line. Returns the exit code."""
    parser = argparse.ArgumentParser(prog="training.train")
    parser.add_argument("examples", type=Path, help="the reviewed JSONL file")
    parser.add_argument("output", type=Path, help="the folder for the adapter")
    parser.add_argument("--base", default=BASE_MODEL)
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--val-share", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args(argv)

    config = replace(
        TrainConfig(), base=args.base, fraction=args.fraction, seed=args.seed
    )
    train, val = split(load_reviewed(args.examples), args.val_share, args.seed)
    used = take_fraction(train, config.fraction, config.seed)
    print(f"{len(used)} training examples, {len(val)} validation examples")
    print(f"Adapter: {train_lora(config, used, val, args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
