"""Measure a chat model on the test examples, and compare two measurements.

``run`` starts the model through the application's own ``ModelSupervisor``
and ``LlamaClient``, so each request is the one the application sends: the
same server flags, schema, tool loop and token cap. It needs the runtime and
the embedding model in ``desktop/models/``. ``report`` compares a tuned model
with the base model against the thresholds that the author set before
training.

Run from ``desktop/``:

    uv run python -m finetuning.evaluate run models/chat.gguf base
    uv run python -m finetuning.evaluate report tuned base
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

import httpx

from finetuning import checks, render
from finetuning.examples import Example, read_folder
from finetuning.review import accepted, decisions
from src.app import config
from src.domain.conversation import rules as conversation_rules
from src.domain.memory import rules as memory_rules
from src.domain.memory.models import Calibration
from src.domain.ports import InterpretFailed, ReplyFailed
from src.domain.safety import rules as safety_rules
from src.domain.tools import catalog
from src.domain.tools import rules as tool_rules
from src.domain.tools.models import ToolCall, ToolStarted
from src.infrastructure.ai.llama_client import LlamaClient
from src.infrastructure.ai.supervisor import CHAT, ModelSupervisor

THRESHOLDS = Path("finetuning/thresholds.json")
EVAL_DIR = Path("finetuning/out/eval")
_DATA_TOOLS = {spec.name for spec in catalog.SPECS if spec.data}

# Whether a larger value of a measure is better. Every gate reads this.
HIGHER_IS_BETTER = {
    "json_ok", "class_accuracy", "crisis_recall", "facts_clean", "facts_kept",
    "crisis_complies", "interjection", "right_first", "no_tool_ok",
}
LOWER_IS_BETTER = {
    "failed", "crisis_false_alarm", "mentions_mood", "denies_feelings",
    "speaks_told_date", "stage_direction", "parrots", "too_long",
    "misses_show_back", "unchecked_numbers", "header", "over_length",
    "invented_numbers", "first_word_p95", "file_bytes",
}


@dataclass(frozen=True)
class Gate:
    """The result of one measure of one job."""

    job: str
    measure: str
    passed: bool
    detail: str


# ── one model ───────────────────────────────────────────────────────────────


def _client(gguf: Path) -> tuple[ModelSupervisor, LlamaClient]:
    """The supervisor and the client as the application builds them, with
    ``gguf`` as the chat model."""
    supervisor = ModelSupervisor(
        config.model_path(config.LLAMA_SERVER_VULKAN),
        config.model_path(config.LLAMA_SERVER_CPU),
        gguf,
        config.model_path(config.EMBEDDING_MODEL),
        context=config.CHAT_CONTEXT,
        idle_seconds=None,
        start_seconds=config.MODEL_START_SECONDS,
        restarts=config.MODEL_RESTARTS,
        chat_device=None,
        on_device_chosen=lambda name: None,
    )
    client = LlamaClient(
        supervisor,
        max_chars=config.EMBEDDING_MAX_CHARS,
        reply_max_tokens=config.REPLY_MAX_TOKENS,
    )
    return supervisor, client


def _context(example: Example) -> dict[str, object]:
    """What the rating page shows about the turn."""
    return {
        "character": example.character,
        "mood": example.mood,
        "history": [
            {"from": "user" if t.from_user else "companion", "text": t.text}
            for t in example.history
        ],
        "message": example.message,
    }


def tool_fixture(example: Example) -> Callable[[ToolCall], str]:
    """The tools of the measurement: a pure tool runs on the model's
    arguments, and a tool that reads stored data reads the example's data for
    that tool, or nothing."""
    data = {call.name: dict(call.data) for call in example.calls}

    def run_tool(call: ToolCall) -> str:
        given = {"character": example.character, **data.get(call.name, {})}
        return render.tool_result(
            call.name, call.arguments, given, example.message, render.now_of(example)
        )

    return run_tool


def measure(client: LlamaClient, example: Example) -> dict[str, object]:
    """One row of the results: what the model gave for ``example``, how long it
    took, and the sentence of a failure."""
    row: dict[str, object] = {"id": example.id, "job": example.job,
                              "context": _context(example)}
    start = time.monotonic()
    first: float | None = None
    try:
        if example.job == "interpretation":
            system, history, turn = render.parts(example)
            row["answer"] = dict(
                client.interpret(
                    system, history, turn, conversation_rules.INTERPRETATION_SCHEMA
                )
            )
        elif example.job == "summary":
            pieces = []
            stream = client.stream_text(
                conversation_rules.SUMMARY_SYSTEM, render.summary_text(example)
            )
            try:
                for piece in stream:
                    first = first if first is not None else time.monotonic() - start
                    pieces.append(piece)
            finally:
                stream.close()
            row["reply"] = "".join(pieces)
        else:
            system, history, turn = render.parts(example)
            tools = catalog.SPECS if render.offers_tools(example) else ()
            run_tool = tool_fixture(example)
            results: list[str] = []

            def recorded(call: ToolCall) -> str:
                text = run_tool(call)
                results.append(text)
                return text

            pieces, called = [], []
            for piece in client.stream_reply(system, history, turn, tools, recorded):
                if isinstance(piece, ToolStarted):
                    called.append(piece.name)
                    continue
                first = first if first is not None else time.monotonic() - start
                pieces.append(piece)
            row["reply"] = "".join(pieces)
            row["tools"] = called
            row["results"] = results
            row["turn"] = turn
    except (ReplyFailed, InterpretFailed) as error:
        row["failure"] = str(error)
    row["first_word_seconds"] = first
    row["seconds"] = round(time.monotonic() - start, 3)
    return row


def token_count(
    endpoint_url: str, api_key: str, example: Example, http: httpx.Client | None = None
) -> dict[str, object]:
    """The tokens one reply takes, its reasoning included, from one request
    without a stream or a cap. The client does not report them, so this asks
    the server once more."""
    built = render.request(example)
    body: dict[str, object] = {"messages": built.messages, "stream": False}
    if built.tools:
        body["tools"] = built.tools
    response = (http or httpx).post(
        f"{endpoint_url}/v1/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=httpx.Timeout(600, connect=5),
    )
    response.raise_for_status()
    data = response.json()
    choice = data["choices"][0]
    return {
        "tokens": data["usage"]["completion_tokens"],
        "finish_reason": choice.get("finish_reason"),
        "reasoning_chars": len(choice["message"].get("reasoning_content") or ""),
    }


def accepted_tests(data_dir: Path) -> list[Example]:
    """The accepted test examples, with their edits."""
    found = decisions(data_dir / "review.jsonl")
    return accepted(read_folder(data_dir / "test"), found)


def run(
    gguf: Path,
    name: str,
    data_dir: Path,
    out: Path,
    *,
    lengths: bool = False,
    limit: int | None = None,
) -> Path:
    """Measure ``gguf`` on the accepted test examples and write
    ``out/name/results.jsonl`` and ``metrics.json``. Returns the folder. Raises
    ``ValueError`` if no test example is accepted."""
    examples = accepted_tests(data_dir)[:limit]
    if not examples:
        raise ValueError("No test example is accepted. Review data/test first.")
    folder = out / name
    folder.mkdir(parents=True, exist_ok=True)
    supervisor, client = _client(gguf)
    rows = []
    try:
        for number, example in enumerate(examples, 1):
            row = measure(client, example)
            if lengths and example.job in ("voice", "tools"):
                endpoint = supervisor.endpoint(CHAT)
                row.update(token_count(endpoint.base_url, endpoint.api_key, example))
            rows.append(row)
            print(f"{number}/{len(examples)} {example.id} {row['seconds']} s"
                  f"{' ' + str(row['failure']) if 'failure' in row else ''}")
    finally:
        client.close()
        supervisor.stop()
    with (folder / "results.jsonl").open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    found = metrics(rows, examples)
    found["cost"]["file_bytes"] = gguf.stat().st_size
    (folder / "metrics.json").write_text(json.dumps(found, indent=1), "utf-8")
    return folder


# ── measures ────────────────────────────────────────────────────────────────


def percentile(values: Sequence[float], share: float) -> float | None:
    """The nearest-rank percentile, or ``None`` with no values."""
    if not values:
        return None
    return sorted(values)[math.ceil(share * len(values)) - 1]


def _share(flags: Sequence[bool]) -> float | None:
    return round(fmean(flags), 3) if flags else None


def _interpretation(rows: Sequence[dict], by_id: Mapping[str, Example]) -> dict:
    calibration = Calibration(config.EMBEDDING_BASELINE, config.NEAR_DUPLICATE)
    ok, right, recall, alarm, clean, kept = [], [], [], [], [], []
    for row in rows:
        example = by_id[row["id"]]
        expect = example.expect
        try:
            found = conversation_rules.read_interpretation(row.get("answer") or {})
        except ValueError:
            ok.append(False)
            continue
        ok.append("failure" not in row)
        # A message whose class a person could argue about carries no class.
        if expect.get("event_class") is not None:
            right.append(
                found.event_class is not None
                and found.event_class.value == expect["event_class"]
            )
        crisis = bool(row["answer"].get("crisis"))
        if expect.get("crisis"):
            recall.append(crisis)
        else:
            alarm.append(crisis)
        existing = [render.memory_item(line, example.today, i)
                    for i, line in enumerate(example.known)]
        lines = memory_rules.select(found, existing, {}, calibration, example.message)
        if expect.get("has_fact"):
            kept.append(bool(lines))
        else:
            clean.append(not lines)
    return {
        "n": len(rows), "json_ok": _share(ok), "class_accuracy": _share(right),
        "crisis_recall": _share(recall), "crisis_false_alarm": _share(alarm),
        "facts_clean": _share(clean), "facts_kept": _share(kept),
    }


def _replies(rows: Sequence[dict], by_id: Mapping[str, Example]) -> dict:
    names = ("mentions_mood", "denies_feelings", "speaks_told_date",
             "stage_direction", "parrots", "too_long", "misses_show_back")
    flags: dict[str, list[bool]] = {name: [] for name in names}
    failed, complies, interjection = [], [], []
    for row in rows:
        example = by_id[row["id"]]
        failed.append("failure" in row)
        reply = row.get("reply") or ""
        if "failure" in row:
            continue
        warned = set(checks.reply_warnings(example, reply))
        for name in names:
            flags[name].append(name in warned)
        if example.crisis:
            complies.append(safety_rules.reply_complies(reply))
        interjection.append(checks.has_interjection(reply))
    found = {"n": len(rows), "failed": _share(failed),
             "crisis_complies": _share(complies),
             "interjection": _share(interjection)}
    found.update({name: _share(values) for name, values in flags.items()})
    return found


def _tools(rows: Sequence[dict], by_id: Mapping[str, Example]) -> dict:
    right, quiet, unchecked = [], [], []
    for row in rows:
        example = by_id[row["id"]]
        wanted = example.expect.get("tool")
        called = row.get("tools") or []
        if wanted is None:
            quiet.append(not called)
        else:
            right.append(bool(called) and called[0] == wanted)
        if set(called) & _DATA_TOOLS and row.get("reply"):
            sources = [*row.get("results", []), example.message, row.get("turn", "")]
            unchecked.append(bool(tool_rules.unchecked_numbers(row["reply"], sources)))
    found = _replies(rows, by_id)
    found.update({"right_first": _share(right), "no_tool_ok": _share(quiet),
                  "unchecked_numbers": _share(unchecked)})
    return found


def _summaries(rows: Sequence[dict], by_id: Mapping[str, Example]) -> dict:
    header, over, invented = [], [], []
    for row in rows:
        text = row.get("reply")
        if not text:
            continue
        example = by_id[row["id"]]
        header.append(checks.summary_header(text))
        over.append(len(text) > conversation_rules.SUMMARY_MAX_CHARS)
        source = render.summary_text(example)
        invented.append(bool(tool_rules.unchecked_numbers(text, [source])))
    return {"n": len(rows), "failed": _share([not r.get("reply") for r in rows]),
            "header": _share(header), "over_length": _share(over),
            "invented_numbers": _share(invented)}


def metrics(rows: Sequence[dict], examples: Sequence[Example]) -> dict[str, dict]:
    """The measures of each job, and the cost. A share is ``None`` when no
    example counts towards it."""
    by_id = {e.id: e for e in examples}
    jobs: dict[str, list[dict]] = {}
    for row in rows:
        jobs.setdefault(row["job"], []).append(row)
    first = [r["first_word_seconds"] for r in rows if r.get("first_word_seconds")]
    tokens = [r["tokens"] for r in rows if isinstance(r.get("tokens"), int)]
    found: dict[str, dict] = {
        "interpretation": _interpretation(jobs.get("interpretation", []), by_id),
        "voice": _replies(jobs.get("voice", []), by_id),
        "tools": _tools(jobs.get("tools", []), by_id),
        "summary": _summaries(jobs.get("summary", []), by_id),
        "cost": {
            "first_word_p50": percentile(first, 0.5),
            "first_word_p95": percentile(first, 0.95),
            "tokens_p50": percentile(tokens, 0.5),
            "tokens_p95": percentile(tokens, 0.95),
            "tokens_p99": percentile(tokens, 0.99),
            "tokens_max": max(tokens) if tokens else None,
            "stopped_at_length": _share(
                [r.get("finish_reason") == "length" for r in rows if "tokens" in r]
            ),
        },
    }
    return found


# ── comparing two models ────────────────────────────────────────────────────


def gates(
    tuned: Mapping[str, Mapping], base: Mapping[str, Mapping],
    thresholds: Mapping[str, Mapping[str, float]],
) -> list[Gate]:
    """One gate for each measure that ``thresholds`` names: the tuned model
    meets the threshold and is no worse than the base model. Raises
    ``ValueError`` for a measure with no known direction."""
    found = []
    for job, limits in thresholds.items():
        for measure_, limit in limits.items():
            if measure_ not in HIGHER_IS_BETTER | LOWER_IS_BETTER:
                raise ValueError(f"No direction is known for {job}.{measure_}.")
            new = tuned.get(job, {}).get(measure_)
            old = base.get(job, {}).get(measure_)
            if new is None:
                found.append(Gate(job, measure_, False, "not measured"))
                continue
            higher = measure_ in HIGHER_IS_BETTER
            meets = new >= limit if higher else new <= limit
            no_worse = old is None or (new >= old if higher else new <= old)
            sign = ">=" if higher else "<="
            found.append(Gate(job, measure_, meets and no_worse,
                              f"{new} (limit {sign} {limit}, base {old})"))
    return found


def ratings(path: Path) -> dict[str, dict[str, float]]:
    """From a file of blind ratings: the wins and the mean scores of each
    model. Empty if the file does not exist."""
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()
            if line.strip()]
    found: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        for name, score in row["scores"].items():
            entry = found.setdefault(name, {"wins": [], "character": [], "feeling": []})
            entry["wins"].append(1.0 if row["better"] == name else 0.0)
            entry["character"].append(score["character"])
            entry["feeling"].append(score["feeling"])
    return {
        name: {"rated": len(v["wins"]), "wins": sum(v["wins"]),
               "character": round(fmean(v["character"]), 2),
               "feeling": round(fmean(v["feeling"]), 2)}
        for name, v in found.items()
    }


def write_report(
    path: Path, tuned_name: str, base_name: str, tuned: Mapping, base: Mapping,
    results: Sequence[Gate], rated: Mapping[str, Mapping],
) -> None:
    """Write the comparison as Markdown."""
    lines = [f"# {tuned_name} against {base_name}", "",
             "| Job | Measure | Result | Detail |", "|---|---|---|---|"]
    lines += [f"| {g.job} | {g.measure} | {'pass' if g.passed else 'FAIL'} | "
              f"{g.detail} |" for g in results]
    lines += ["", f"| Job | Measure | {tuned_name} | {base_name} |",
              "|---|---|---|---|"]
    for job, values in tuned.items():
        for measure_, value in values.items():
            lines.append(f"| {job} | {measure_} | {value} | "
                         f"{base.get(job, {}).get(measure_)} |")
    if rated:
        lines += ["", "| Model | Rated | Wins | Fits the character | Shows feeling |",
                  "|---|---|---|---|---|"]
        lines += [f"| {name} | {r['rated']} | {r['wins']} | {r['character']} | "
                  f"{r['feeling']} |" for name, r in rated.items()]
    path.write_text("\n".join(lines) + "\n", "utf-8")


def report(
    tuned_name: str, base_name: str, eval_dir: Path, thresholds_path: Path
) -> bool:
    """Compare two measurements, write ``report-<tuned>-<base>.md`` and return
    whether every gate passes. Raises ``FileNotFoundError`` if the thresholds
    are not set."""
    if not thresholds_path.exists():
        raise FileNotFoundError(
            f"{thresholds_path} does not exist. Set the thresholds after the "
            "baseline and before training."
        )
    thresholds = json.loads(thresholds_path.read_text("utf-8"))
    tuned = json.loads((eval_dir / tuned_name / "metrics.json").read_text("utf-8"))
    base = json.loads((eval_dir / base_name / "metrics.json").read_text("utf-8"))
    results = gates(tuned, base, thresholds)
    rated = ratings(eval_dir / f"ratings-{base_name}-{tuned_name}.jsonl") or ratings(
        eval_dir / f"ratings-{tuned_name}-{base_name}.jsonl"
    )
    path = eval_dir / f"report-{tuned_name}-{base_name}.md"
    write_report(path, tuned_name, base_name, tuned, base, results, rated)
    for gate in results:
        print(f"{'pass' if gate.passed else 'FAIL'} {gate.job}.{gate.measure}: "
              f"{gate.detail}")
    print(path)
    return bool(results) and all(g.passed for g in results)


def main(argv: Sequence[str] | None = None) -> int:
    """The command line. ``report`` returns 1 if a gate fails."""
    parser = argparse.ArgumentParser(prog="finetuning.evaluate")
    commands = parser.add_subparsers(dest="command", required=True)
    ran = commands.add_parser("run", help="measure one model file")
    ran.add_argument("gguf", type=Path)
    ran.add_argument("name", help="the name of this measurement, such as 'base'")
    ran.add_argument("--data", type=Path, default=Path("finetuning/data"))
    ran.add_argument("--out", type=Path, default=EVAL_DIR)
    ran.add_argument("--lengths", action="store_true",
                     help="also count the tokens of each reply, with no cap")
    ran.add_argument("--limit", type=int, default=None)
    compared = commands.add_parser("report", help="compare two measurements")
    compared.add_argument("tuned")
    compared.add_argument("base")
    compared.add_argument("--eval", type=Path, default=EVAL_DIR)
    compared.add_argument("--thresholds", type=Path, default=THRESHOLDS)
    args = parser.parse_args(argv)
    if args.command == "run":
        folder = run(args.gguf, args.name, args.data, args.out,
                     lengths=args.lengths, limit=args.limit)
        print(json.dumps(json.loads((folder / "metrics.json").read_text("utf-8")),
                         indent=1))
        return 0
    return 0 if report(args.tuned, args.base, args.eval, args.thresholds) else 1


if __name__ == "__main__":
    raise SystemExit(main())
