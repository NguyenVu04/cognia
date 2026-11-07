"""A page on this machine for reviewing examples, and for rating two models.

``review`` shows each example as the model will see it, with the warnings of
``finetuning.checks``, and records accept, reject and edits in
``data/review.jsonl``. The example files never change: the newest decision for
an ID wins. ``rate`` shows the replies of two measured models side by side, in
a random order and with no names, and records which one reads better.

The server listens on 127.0.0.1 only. Run from ``desktop/``:

    uv run python -m finetuning.review review finetuning/data
    uv run python -m finetuning.review rate base tuned
"""

from __future__ import annotations

import argparse
import json
import random
import webbrowser
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlsplit

from finetuning import checks, render
from finetuning.examples import Example, read_folder, to_json, validate

HOST = "127.0.0.1"
PAGE = Path(__file__).with_name("review_page.html")
PARTS = ("seeds", "train", "test")
STATUSES = ("accepted", "rejected")


@dataclass(frozen=True)
class Decision:
    """What the reviewer decided about one example. An edit replaces the
    reasoning or the target; ``None`` keeps the example's own."""

    id: str
    status: str
    at: str
    reasoning: str | None = None
    target: str | dict | None = None
    note: str = ""


def decisions(path: Path) -> dict[str, Decision]:
    """The newest decision for each ID in ``path``. Empty if the file does not
    exist."""
    found: dict[str, Decision] = {}
    if not path.exists():
        return found
    for line in path.read_text("utf-8").splitlines():
        if line.strip():
            decision = Decision(**json.loads(line))
            found[decision.id] = decision
    return found


def record(path: Path, decision: Decision) -> None:
    """Add ``decision`` at the end of ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(asdict(decision), ensure_ascii=False) + "\n")


def apply(example: Example, decision: Decision | None) -> Example:
    """``example`` with the reviewer's edits."""
    if decision is None:
        return example
    changes: dict[str, object] = {}
    if decision.reasoning is not None:
        changes["reasoning"] = decision.reasoning
    if decision.target is not None:
        changes["target"] = decision.target
    return replace(example, **changes)


def accepted(
    examples: Sequence[Example], found: Mapping[str, Decision]
) -> list[Example]:
    """The accepted examples, with their edits."""
    return [
        apply(e, found[e.id])
        for e in examples
        if e.id in found and found[e.id].status == "accepted"
    ]


class ReviewError(ValueError):
    """A request that the page cannot carry out, with a sentence saying why."""


class Review:
    """The examples under one data folder and the decisions about them."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "review.jsonl"
        self._lock = Lock()
        self.examples: dict[str, tuple[str, Example]] = {}
        for part in PARTS:
            for example in read_folder(data_dir / part):
                self.examples[example.id] = (part, example)

    def _status(self, found: Mapping[str, Decision], example_id: str) -> str:
        decision = found.get(example_id)
        return decision.status if decision else "pending"

    def listing(self, query: Mapping[str, str]) -> dict[str, object]:
        """The examples that match the filters, and the progress of each job."""
        found = decisions(self.path)
        rows, progress = [], {}
        for example_id, (part, example) in self.examples.items():
            status = self._status(found, example_id)
            shown = apply(example, found.get(example_id))
            warned = checks.warnings(shown)
            done = progress.setdefault(f"{part}/{example.job}", [0, 0])
            done[1] += 1
            done[0] += status != "pending"
            if query.get("part") and query["part"] != part:
                continue
            if query.get("job") and query["job"] != example.job:
                continue
            if query.get("status") and query["status"] != status:
                continue
            if query.get("warn") and query["warn"] not in warned:
                continue
            rows.append(
                {"id": example_id, "part": part, "job": example.job,
                 "character": example.character, "status": status,
                 "warnings": warned}
            )
        return {"examples": rows, "progress": progress}

    def detail(self, example_id: str) -> dict[str, object]:
        """One example with its prompt, its answer, its warnings and errors.
        Raises :class:`ReviewError` for an unknown ID."""
        if example_id not in self.examples:
            raise ReviewError(f"No example has the ID {example_id!r}.")
        part, example = self.examples[example_id]
        decision = decisions(self.path).get(example_id)
        shown = apply(example, decision)
        built = render.request(shown)
        return {
            "id": example_id,
            "part": part,
            "status": decision.status if decision else "pending",
            "note": decision.note if decision else "",
            "example": to_json(shown),
            "messages": built.messages,
            "tools": [t["function"]["name"] for t in built.tools],
            "answer": render.answer(shown) if shown.target is not None else [],
            "warnings": checks.warnings(shown),
            "errors": validate(shown, test=part == "test"),
        }

    def decide(self, body: Mapping[str, object]) -> dict[str, object]:
        """Record a decision and return the example as it now is. Raises
        :class:`ReviewError` for an unknown ID or status, a target that is not
        JSON on an interpretation, or an accepted example with errors."""
        example_id = str(body.get("id", ""))
        status = str(body.get("status", ""))
        if example_id not in self.examples:
            raise ReviewError(f"No example has the ID {example_id!r}.")
        if status not in STATUSES:
            raise ReviewError(f"The status is one of {', '.join(STATUSES)}.")
        part, example = self.examples[example_id]
        target = body.get("target")
        if example.job == "interpretation" and isinstance(target, str):
            try:
                target = json.loads(target)
            except ValueError as error:
                raise ReviewError(f"The target is not JSON: {error}.") from error
        reasoning = body.get("reasoning")
        decision = Decision(
            id=example_id,
            status=status,
            at=datetime.now(UTC).isoformat(timespec="seconds"),
            reasoning=None if reasoning is None else str(reasoning),
            target=target,  # type: ignore[arg-type]
            note=str(body.get("note") or ""),
        )
        if status == "accepted":
            errors = validate(apply(example, decision), test=part == "test")
            if errors:
                raise ReviewError("Not accepted: " + "; ".join(errors))
        with self._lock:
            record(self.path, decision)
        return self.detail(example_id)


class Rating:
    """The voice replies of two measured models, shown blind, and the scores."""

    def __init__(self, eval_dir: Path, first: str, second: str, seed: int = 1) -> None:
        self.path = eval_dir / f"ratings-{first}-{second}.jsonl"
        self._lock = Lock()
        a = _replies(eval_dir / first / "results.jsonl")
        b = _replies(eval_dir / second / "results.jsonl")
        rng = random.Random(seed)
        self.pairs: dict[str, dict[str, object]] = {}
        for example_id in sorted(set(a) & set(b)):
            names = [first, second]
            rng.shuffle(names)
            shown = {first: a[example_id], second: b[example_id]}
            self.pairs[example_id] = {
                "names": names,
                "context": a[example_id]["context"],
                "replies": [shown[n]["reply"] for n in names],
            }

    def listing(self) -> dict[str, object]:
        """Every pair, without the model names, and which are rated."""
        done = set()
        if self.path.exists():
            done = {json.loads(line)["id"] for line in
                    self.path.read_text("utf-8").splitlines() if line.strip()}
        return {
            "pairs": [
                {"id": example_id, "context": pair["context"],
                 "replies": pair["replies"], "rated": example_id in done}
                for example_id, pair in self.pairs.items()
            ]
        }

    def rate(self, body: Mapping[str, object]) -> None:
        """Record the scores of one pair. Raises :class:`ReviewError` for an
        unknown pair or a score outside 1 to 5."""
        example_id = str(body.get("id", ""))
        pair = self.pairs.get(example_id)
        if pair is None:
            raise ReviewError(f"No pair has the ID {example_id!r}.")
        better = body.get("better")
        if better not in (0, 1, None):
            raise ReviewError("'better' is 0, 1 or null.")
        scores = body.get("scores")
        if (
            not isinstance(scores, list)
            or len(scores) != 2
            or not all(
                isinstance(s, dict)
                and all(s.get(k) in range(1, 6) for k in ("character", "feeling"))
                for s in scores
            )
        ):
            raise ReviewError("Each reply needs a 'character' and a 'feeling' score "
                              "from 1 to 5.")
        names = pair["names"]
        row = {
            "id": example_id,
            "better": None if better is None else names[better],  # type: ignore[index]
            "scores": {names[i]: scores[i] for i in range(2)},  # type: ignore[index]
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(row) + "\n")


def _replies(path: Path) -> dict[str, dict[str, object]]:
    """The voice replies of one measurement, by example ID."""
    found = {}
    if not path.exists():
        return found
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("job") == "voice" and row.get("reply"):
            found[row["id"]] = {"reply": row["reply"], "context": row.get("context")}
    return found


class _Handler(BaseHTTPRequestHandler):
    review: Review | None = None
    rating: Rating | None = None

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # the terminal stays quiet

    def _send(self, status: int, body: object, kind: str = "application/json") -> None:
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - the name http.server calls
        url = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/":
                mode = "rate" if self.rating else "review"
                page = PAGE.read_text("utf-8").replace("{{MODE}}", mode)
                self._send(HTTPStatus.OK, page, "text/html")
            elif url.path == "/api/examples" and self.review:
                self._send(HTTPStatus.OK, self.review.listing(query))
            elif url.path == "/api/example" and self.review:
                self._send(HTTPStatus.OK, self.review.detail(query.get("id", "")))
            elif url.path == "/api/pairs" and self.rating:
                self._send(HTTPStatus.OK, self.rating.listing())
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Not found."})
        except ReviewError as error:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def do_POST(self) -> None:  # noqa: N802 - the name http.server calls
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ReviewError("The body is not a JSON object.")
            if self.path == "/api/decision" and self.review:
                self._send(HTTPStatus.OK, self.review.decide(body))
            elif self.path == "/api/rate" and self.rating:
                self.rating.rate(body)
                self._send(HTTPStatus.OK, {"ok": True})
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Not found."})
        except (ReviewError, ValueError) as error:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})


def make_server(
    review: Review | None = None, rating: Rating | None = None, port: int = 0
) -> ThreadingHTTPServer:
    """A server on 127.0.0.1 for ``review`` or ``rating``. Port 0 takes a free
    port; ``server_address`` names it."""
    handler = type("Handler", (_Handler,), {"review": review, "rating": rating})
    return ThreadingHTTPServer((HOST, port), handler)


def _serve(server: ThreadingHTTPServer, open_browser: bool) -> None:
    url = f"http://{HOST}:{server.server_address[1]}/"
    print(f"Open {url} — Ctrl+C stops the server.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: Sequence[str] | None = None) -> int:
    """The command line."""
    parser = argparse.ArgumentParser(prog="finetuning.review")
    commands = parser.add_subparsers(dest="command", required=True)
    reviewed = commands.add_parser("review", help="review the examples")
    reviewed.add_argument("data", type=Path, help="the data folder")
    rated = commands.add_parser("rate", help="rate two measured models, blind")
    rated.add_argument("first")
    rated.add_argument("second")
    rated.add_argument("--eval", type=Path, default=Path("finetuning/out/eval"))
    rated.add_argument("--seed", type=int, default=1)
    for command in (reviewed, rated):
        command.add_argument("--port", type=int, default=0)
        command.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "review":
        server = make_server(review=Review(args.data), port=args.port)
    else:
        rating = Rating(args.eval, args.first, args.second, args.seed)
        if not rating.pairs:
            print(f"No voice reply is in both {args.first} and {args.second}.")
            return 1
        server = make_server(rating=rating, port=args.port)
    _serve(server, not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
