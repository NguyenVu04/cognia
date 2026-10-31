"""Merge, quantise, write the licence files (ARCHITECTURE.md, section 8.4).

Run from ``desktop/``, on a machine with a GPU:

    uv run --project training --extra gpu python -m training.export \\
        ADAPTER OUTPUT LICENCE --base-date YYYY-MM-DD
"""

from __future__ import annotations

import argparse
import shutil
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from training.train import BASE_MODEL

CHAT_FILE = "chat.gguf"


def _name_chat_file(output: Path) -> Path:
    # A vision projector can sit beside the model, and Cognia does not load it.
    files = [path for path in output.glob("*.gguf") if "mmproj" not in path.name]
    if len(files) != 1:
        raise ValueError(f"Expected one model file in {output}, found {len(files)}.")
    return files[0].replace(output / CHAT_FILE)


def merge_and_quantise(adapter: Path, method: str, output: Path) -> Path:
    """Merge ``adapter`` into its base, quantise by ``method``, and return the
    path of ``chat.gguf`` in ``output``. Needs the ``gpu`` extra and a GPU."""
    # Imported here so that the tests need no torch.
    from unsloth import FastModel

    model, tokenizer = FastModel.from_pretrained(
        model_name=str(adapter), load_in_4bit=False
    )
    model.save_pretrained_gguf(str(output), tokenizer, quantization_method=method)
    return _name_chat_file(output)


def write_licences(
    output: Path, licence_source: Path, base: str, base_date: date
) -> None:
    """Write the licence text and a notice that the weights are modified, with the
    source and date of the base model (Apache-2.0 section 4). Raises
    ``FileNotFoundError`` if ``licence_source`` does not exist."""
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(licence_source, output / "LICENSE.txt")
    (output / "NOTICE.txt").write_text(
        f"{CHAT_FILE} holds modified weights.\n"
        f"Base model: {base}\n"
        f"Base model date: {base_date.isoformat()}\n"
        "Change: a LoRA adapter was trained on synthetic examples and merged "
        "into the base model, for the Cognia project.\n",
        "utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """The command line. Returns the exit code."""
    parser = argparse.ArgumentParser(prog="training.export")
    parser.add_argument("adapter", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("licence", type=Path, help="the LICENSE file of the base model")
    parser.add_argument("--base", default=BASE_MODEL)
    parser.add_argument("--base-date", type=date.fromisoformat, required=True)
    parser.add_argument("--method", default="q4_k_m")
    args = parser.parse_args(argv)

    chat_file = merge_and_quantise(args.adapter, args.method, args.output)
    write_licences(args.output, args.licence, args.base, args.base_date)
    print(chat_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
