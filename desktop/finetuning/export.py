"""Merge the adapter, quantise, and write the licence files.

Run from ``desktop/``, on the machine that trained:

    uv run --project finetuning --extra gpu python -m finetuning.export \\
        finetuning/out/adapter finetuning/out/merged LICENSE --base-date YYYY-MM-DD

OUTPUT receives the merged checkpoint. ``chat.gguf`` and the licence files land
in the sibling ``OUTPUT_gguf``.
"""

from __future__ import annotations

import argparse
import shutil
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from finetuning.train import BASE_MODEL

CHAT_FILE = "chat.gguf"


def gguf_directory(output: Path) -> Path:
    """Where Unsloth writes the GGUF files: a sibling it names itself."""
    return output.with_name(output.name + "_gguf")


def name_chat_file(folder: Path) -> Path:
    """Rename the one model file in ``folder`` to ``chat.gguf`` and return it.
    A vision projector can sit beside it, and Cognia does not load it. Raises
    ``ValueError`` unless there is exactly one model file."""
    files = [path for path in folder.glob("*.gguf")
             if "mmproj" not in path.name and path.name != CHAT_FILE]
    if (folder / CHAT_FILE).exists() and not files:
        return folder / CHAT_FILE
    if len(files) != 1:
        raise ValueError(f"Expected one model file in {folder}, found {len(files)}.")
    return files[0].replace(folder / CHAT_FILE)


def merge_and_quantise(adapter: Path, method: str, output: Path) -> Path:
    """Merge ``adapter`` into its base in ``output``, quantise by ``method``, and
    return the path of ``chat.gguf``. Needs the ``gpu`` extra and a GPU."""
    # Imported here so that the tests need no torch.
    from unsloth import FastModel

    model, tokenizer = FastModel.from_pretrained(
        model_name=str(adapter), load_in_4bit=False
    )
    model.save_pretrained_gguf(str(output), tokenizer, quantization_method=method)
    return name_chat_file(gguf_directory(output))


def write_licences(
    output: Path, licence_source: Path, base: str, base_date: date
) -> None:
    """Write the licence text and a notice that the weights are modified, with
    the source and date of the base model, as the Apache licence asks. Raises
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
    parser = argparse.ArgumentParser(prog="finetuning.export")
    parser.add_argument("adapter", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("licence", type=Path, help="the LICENSE file of the base model")
    parser.add_argument("--base", default=BASE_MODEL)
    parser.add_argument("--base-date", type=date.fromisoformat, required=True)
    parser.add_argument("--method", default="q4_k_m")
    args = parser.parse_args(argv)

    chat_file = merge_and_quantise(args.adapter, args.method, args.output)
    write_licences(chat_file.parent, args.licence, args.base, args.base_date)
    print(chat_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
