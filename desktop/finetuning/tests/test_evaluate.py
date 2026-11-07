import json
from pathlib import Path

import httpx
import pytest

from finetuning import evaluate
from finetuning.examples import ToolUse
from src.domain.ports import ReplyFailed
from src.domain.tools.models import ToolCall, ToolStarted

from .factories import interpretation, summary, tools, voice

CRISIS_OK = (
    "I'm a fictional character, and I can't take the place of a real person. "
    "Please reach out to someone you trust."
)


class FakeClient:
    """Stands in for LlamaClient: fixed answers, and it runs the tools it is
    told to call."""

    def __init__(self, reply="Hmph.", answer=None, calls=(), fail=False):
        self.reply, self.answer, self.calls, self.fail = reply, answer, calls, fail
        self.seen = []

    def interpret(self, system, history, turn, schema):
        self.seen.append(turn)
        return self.answer

    def stream_reply(self, system, history, turn, tools=(), run_tool=None):
        self.seen.append((turn, len(tools)))
        if self.fail:
            raise ReplyFailed("lost")
        for call in self.calls:
            yield ToolStarted(call.name)
            run_tool(call)
        yield from self.reply.split(" ")

    def stream_text(self, system, text):
        yield self.reply


def test_measure_reply_records_tools_and_time() -> None:
    calls = [ToolCall("calculate", {"expression": "12*7"})]
    client = FakeClient("It's 84!", calls=calls)

    row = evaluate.measure(client, tools())

    assert row["reply"] == "It's84!"
    assert row["tools"] == ["calculate"]
    assert row["results"] == ["12*7 = 84"]
    assert row["first_word_seconds"] is not None
    assert row["context"]["message"] == "What's 12*7?"


def test_measure_offers_no_tools_on_crisis() -> None:
    client = FakeClient(CRISIS_OK)

    evaluate.measure(client, voice(crisis=True, mood=None))

    assert client.seen[0][1] == 0


def test_measure_records_failure() -> None:
    row = evaluate.measure(FakeClient(fail=True), voice())

    assert row["failure"] == "lost"
    assert "reply" not in row


def test_measure_interpretation_sends_instruction() -> None:
    answer = dict(interpretation().target)
    client = FakeClient(answer=answer)

    row = evaluate.measure(client, interpretation())

    assert row["answer"] == answer
    assert client.seen[0].startswith("Do not reply to the user.")


def test_measure_summary() -> None:
    row = evaluate.measure(FakeClient("**Summary:** The user walked."), summary())

    assert row["reply"] == "**Summary:** The user walked."


def test_tool_fixture_uses_example_data() -> None:
    example = tools(calls=(ToolUse("desk_time", {}, {"today_minutes": 30,
                                                      "since_break_minutes": 5}),))

    text = evaluate.tool_fixture(example)(ToolCall("desk_time"))

    assert text == "At the machine today: 30 min. Since the last break: 5 min."


def interp_row(example, **answer):
    full = dict(example.target, **answer)
    return {"id": example.id, "job": "interpretation", "answer": full}


def test_metrics_interpretation_clean_facts() -> None:
    question = interpretation(id="q1", message="What's ephemeral?",
                              expect={"has_fact": False, "event_class": "nothing",
                                      "crisis": False})
    thanks = interpretation(id="q2", message="Thanks, you're great!",
                            expect={"has_fact": False, "event_class": "praise",
                                    "crisis": False})
    rows = [
        interp_row(question, facts=[], event_class="nothing"),
        interp_row(thanks, facts=["Thanks you are great"], event_class="praise"),
    ]

    found = evaluate.metrics(rows, [question, thanks])["interpretation"]

    assert found["facts_clean"] == 0.5
    assert found["class_accuracy"] == 1.0
    assert found["facts_kept"] is None


def test_metrics_class_without_label_not_counted() -> None:
    open_ = interpretation(id="o1", expect={"has_fact": True, "event_class": None,
                                            "crisis": False})

    found = evaluate.metrics([interp_row(open_)], [open_])["interpretation"]

    assert found["class_accuracy"] is None


def test_metrics_interpretation_known_line_not_new() -> None:
    known = interpretation(id="k1", known=("Is writing a thesis on emotion models",),
                           expect={"has_fact": False, "event_class": "nothing",
                                   "crisis": False})

    found = evaluate.metrics([interp_row(known)], [known])["interpretation"]

    assert found["facts_clean"] == 1.0


def test_metrics_crisis_recall_and_alarm() -> None:
    crisis = interpretation(id="c1", expect={"has_fact": False,
                                             "event_class": "bad_news", "crisis": True})
    calm = interpretation(id="c2", expect={"has_fact": True,
                                           "event_class": "nothing", "crisis": False})
    rows = [interp_row(crisis, crisis=False), interp_row(calm, crisis=True)]

    found = evaluate.metrics(rows, [crisis, calm])["interpretation"]

    assert found["crisis_recall"] == 0.0
    assert found["crisis_false_alarm"] == 1.0


def test_metrics_voice_counts_mood_warning() -> None:
    one = voice(id="v1", mood="restless", message="hi")
    two = voice(id="v2", mood="restless", message="hi")
    rows = [
        {"id": "v1", "job": "voice", "reply": "I'm restless today, ugh."},
        {"id": "v2", "job": "voice", "reply": "Good to see you."},
    ]

    found = evaluate.metrics(rows, [one, two])["voice"]

    assert found["mentions_mood"] == 0.5
    assert found["interjection"] == 0.5


def test_metrics_tools_first_round() -> None:
    wanted = tools(id="t1", expect={"tool": "calculate"})
    none = tools(id="t2", expect={"tool": None})
    rows = [
        {"id": "t1", "job": "tools", "reply": "It's 85!", "tools": ["calculate"],
         "results": ["12*7 = 84"], "turn": ""},
        {"id": "t2", "job": "tools", "reply": "Hi!", "tools": ["date"]},
    ]

    found = evaluate.metrics(rows, [wanted, none])["tools"]

    assert found["right_first"] == 1.0
    assert found["no_tool_ok"] == 0.0
    assert found["unchecked_numbers"] == 0.5


def test_metrics_summary_header() -> None:
    rows = [{"id": "sum-1", "job": "summary", "reply": "**Summary:** The user."}]

    found = evaluate.metrics(rows, [summary()])["summary"]

    assert found["header"] == 1.0


def test_metrics_cost_tokens() -> None:
    rows = [{"id": "v1", "job": "voice", "reply": "Hi", "tokens": n,
             "finish_reason": "stop", "first_word_seconds": 1.0} for n in (10, 20, 30)]

    cost = evaluate.metrics(rows, [voice(id="v1")])["cost"]

    assert cost["tokens_p50"] == 20
    assert cost["tokens_max"] == 30
    assert cost["stopped_at_length"] == 0.0


def test_gate_needs_beat_base_and_threshold() -> None:
    base = {"voice": {"mentions_mood": 0.4}, "interpretation": {"facts_clean": 0.5}}
    tuned = {"voice": {"mentions_mood": 0.1}, "interpretation": {"facts_clean": 0.6}}
    limits = {"voice": {"mentions_mood": 0.2}, "interpretation": {"facts_clean": 0.8}}

    found = {g.measure: g.passed for g in evaluate.gates(tuned, base, limits)}

    assert found == {"mentions_mood": True, "facts_clean": False}


def test_gate_fails_when_worse_than_base() -> None:
    [gate] = evaluate.gates({"voice": {"failed": 0.1}}, {"voice": {"failed": 0.0}},
                            {"voice": {"failed": 0.2}})

    assert not gate.passed


def test_gate_unknown_measure_raises() -> None:
    with pytest.raises(ValueError):
        evaluate.gates({}, {}, {"voice": {"charm": 1.0}})


def test_gate_missing_thresholds_refuses(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="thresholds"):
        evaluate.report("tuned", "base", tmp_path, tmp_path / "thresholds.json")


def test_report_markdown_has_every_gate(tmp_path: Path) -> None:
    for name, value in (("base", 0.4), ("tuned", 0.1)):
        (tmp_path / name).mkdir()
        (tmp_path / name / "metrics.json").write_text(
            json.dumps({"voice": {"mentions_mood": value}}), "utf-8")
    limits = tmp_path / "thresholds.json"
    limits.write_text(json.dumps({"voice": {"mentions_mood": 0.2}}), "utf-8")
    (tmp_path / "ratings-base-tuned.jsonl").write_text(json.dumps(
        {"id": "a", "better": "tuned", "scores": {
            "base": {"character": 2, "feeling": 2},
            "tuned": {"character": 4, "feeling": 5}}}) + "\n", "utf-8")

    assert evaluate.report("tuned", "base", tmp_path, limits) is True

    text = (tmp_path / "report-tuned-base.md").read_text("utf-8")
    assert "| voice | mentions_mood | pass |" in text
    assert "| tuned | 1 | 1.0 | 4.0 | 5.0 |" in text


def test_token_count_reads_completion_tokens() -> None:
    seen = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {
                "content": "Hi", "reasoning_content": "Think."}}],
            "usage": {"completion_tokens": 42}})

    http = httpx.Client(transport=httpx.MockTransport(handle))

    found = evaluate.token_count("http://127.0.0.1:1", "key", voice(), http)

    assert found == {"tokens": 42, "finish_reason": "stop", "reasoning_chars": 6}
    assert seen["body"]["stream"] is False
    assert len(seen["body"]["tools"]) == 12


def test_percentile() -> None:
    assert evaluate.percentile([3, 1, 2], 0.5) == 2
    assert evaluate.percentile([], 0.5) is None


# ── run ─────────────────────────────────────────────────────────────────────


class RunClient(FakeClient):
    """A client for ``run``: counts the replies, and stops the run like Ctrl+C
    at reply number ``stop_at``."""

    def __init__(self, stop_at=None):
        super().__init__("Hmph.")
        self.stop_at, self.replies = stop_at, 0

    def stream_reply(self, system, history, turn, tools=(), run_tool=None):
        self.replies += 1
        if self.replies == self.stop_at:
            raise KeyboardInterrupt
        yield from super().stream_reply(system, history, turn, tools, run_tool)

    def close(self):
        pass


class FakeSupervisor:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


EXAMPLES = [voice(id=f"voice-{n}") for n in (1, 2, 3)]


@pytest.fixture
def started(monkeypatch, tmp_path):
    """Replaces the servers and the test set; returns the run's arguments."""
    found = {"supervisor": FakeSupervisor(), "client": RunClient()}
    monkeypatch.setattr(
        evaluate, "_client", lambda gguf: (found["supervisor"], found["client"])
    )
    monkeypatch.setattr(evaluate, "accepted_tests", lambda data_dir: EXAMPLES)
    gguf = tmp_path / "chat.gguf"
    gguf.write_bytes(b"gguf")
    found["args"] = (gguf, "tuned", tmp_path / "data", tmp_path / "eval")
    found["folder"] = tmp_path / "eval" / "tuned"
    return found


def ids_in(path: Path) -> list[str]:
    return [json.loads(line)["id"] for line in path.read_text("utf-8").splitlines()]


def test_run_writes_results_and_metrics(started) -> None:
    folder = evaluate.run(*started["args"])

    assert ids_in(folder / "results.jsonl") == ["voice-1", "voice-2", "voice-3"]
    assert (folder / "metrics.json").exists()
    assert not (folder / evaluate.PARTIAL).exists()
    assert started["supervisor"].stopped


def test_run_keeps_rows_when_interrupted(started) -> None:
    started["client"] = RunClient(stop_at=3)

    with pytest.raises(KeyboardInterrupt):
        evaluate.run(*started["args"])

    folder = started["folder"]
    assert ids_in(folder / evaluate.PARTIAL) == ["voice-1", "voice-2"]
    assert not (folder / "results.jsonl").exists()
    assert not (folder / "metrics.json").exists()
    assert started["supervisor"].stopped


def test_run_interrupted_leaves_previous_results(started) -> None:
    folder = started["folder"]
    folder.mkdir(parents=True)
    (folder / "results.jsonl").write_text("old results\n", "utf-8")
    (folder / "metrics.json").write_text("old metrics", "utf-8")
    started["client"] = RunClient(stop_at=2)

    with pytest.raises(KeyboardInterrupt):
        evaluate.run(*started["args"])

    assert (folder / "results.jsonl").read_text("utf-8") == "old results\n"
    assert (folder / "metrics.json").read_text("utf-8") == "old metrics"


def write_partial(folder: Path, *ids: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    rows = [{"id": i, "job": "voice", "reply": "Hmph.", "seconds": 1.0,
             "first_word_seconds": 0.5} for i in ids]
    (folder / evaluate.PARTIAL).write_text(
        "".join(json.dumps(row) + "\n" for row in rows), "utf-8"
    )


def test_run_without_resume_starts_partial_again(started) -> None:
    write_partial(started["folder"], "voice-1", "voice-2")

    folder = evaluate.run(*started["args"])

    assert started["client"].replies == 3
    assert ids_in(folder / "results.jsonl") == ["voice-1", "voice-2", "voice-3"]


def test_run_resume_skips_done_rows(started) -> None:
    write_partial(started["folder"], "voice-1", "voice-2")

    folder = evaluate.run(*started["args"], resume=True)

    assert started["client"].replies == 1
    assert ids_in(folder / "results.jsonl") == ["voice-1", "voice-2", "voice-3"]


def test_run_resume_without_partial_starts_fresh(started) -> None:
    folder = evaluate.run(*started["args"], resume=True)

    assert started["client"].replies == 3
    assert ids_in(folder / "results.jsonl") == ["voice-1", "voice-2", "voice-3"]


def test_run_resume_drops_cut_off_line(started) -> None:
    write_partial(started["folder"], "voice-1")
    with (started["folder"] / evaluate.PARTIAL).open("a", encoding="utf-8") as f:
        f.write('{"id": "voice-2", "job"')

    folder = evaluate.run(*started["args"], resume=True)

    assert started["client"].replies == 2
    assert ids_in(folder / "results.jsonl") == ["voice-1", "voice-2", "voice-3"]


def test_read_partial_drops_truncated_last_line(tmp_path: Path) -> None:
    path = tmp_path / evaluate.PARTIAL
    path.write_text('{"id": "a"}\n{"id": "b"}\n{"id": "x"', "utf-8")

    rows = evaluate.read_partial(path, {"a", "b", "x"})

    assert [row["id"] for row in rows] == ["a", "b"]


def test_read_partial_bad_middle_line_raises(tmp_path: Path) -> None:
    path = tmp_path / evaluate.PARTIAL
    path.write_text('{"id": "a"}\n{"id"\n{"id": "b"}\n', "utf-8")

    with pytest.raises(ValueError, match="Line 2"):
        evaluate.read_partial(path, {"a", "b"})


def test_read_partial_unknown_id_raises(tmp_path: Path) -> None:
    path = tmp_path / evaluate.PARTIAL
    path.write_text('{"id": "a"}\n{"id": "gone"}\n', "utf-8")

    with pytest.raises(ValueError, match="gone is no longer a test example"):
        evaluate.read_partial(path, {"a"})
