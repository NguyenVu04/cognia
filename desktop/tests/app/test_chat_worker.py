import math
from concurrent.futures import Future
from datetime import date, datetime, timezone

import pytest

from src.app import chat_worker
from src.app.chat_worker import (
    ChatWorker,
    Prepared,
    Replied,
    ReplyRequest,
    SummaryDone,
    SummaryJob,
    TurnRequest,
)
from src.domain.conversation.models import USER, Message
from src.domain.memory import rules as memory_rules
from src.domain.memory.models import TOLD, Calibration, MemoryItem
from src.domain.ports import EmbedFailed, InterpretFailed, ReplyFailed
from src.domain.tools import catalog
from src.domain.tools import rules as tool_rules
from src.domain.tools.models import ToolCall, ToolResult, ToolStarted

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
CAL = Calibration(0.45, 0.95)
MESSAGE = Message("m1", "c", USER, "I sent chapter 3 to my supervisor!", NOW)
THESIS = MemoryItem(
    id="i1", kind=TOLD, text="Is writing a thesis", reason=None,
    source_message_id=None, importance=8, last_retrieved_at=NOW, recorded_at=NOW,
    embedding=(0.8, math.sqrt(1 - 0.64)),
)
ANSWER = {
    "event_class": "good_news", "confidence": 0.9, "importance": 8, "crisis": False,
    "facts": ["Has a supervisor"],
    "style_request": None,
}


class FakeEmbedder:
    def __init__(self, failing: bool = False) -> None:
        self.failing = failing
        self.calls: list[list[str]] = []

    def embed(self, texts):
        self.calls.append(list(texts))
        if self.failing:
            raise EmbedFailed("down")
        return [(1.0, 0.0) for _ in texts]


class FakeInterpreter:
    def __init__(self, answer=None, failing: bool = False) -> None:
        self.answer = ANSWER if answer is None else answer
        self.failing = failing
        self.turns: list[str] = []

    def interpret(self, system_prompt, history, turn, schema):
        self.turns.append(turn)
        if self.failing:
            raise InterpretFailed("no")
        return self.answer


class FakeReplier:
    def __init__(self, pieces=("Hel", "lo"), failure: str | None = None) -> None:
        self.pieces = pieces
        self.failure = failure
        self.turns: list[str] = []

    def stream_reply(self, system_prompt, history, turn, tools=(), run_tool=None):
        self.turns.append(turn)
        self.tools = tuple(tools)
        if self.failure:
            raise ReplyFailed(self.failure)
        yield from self.pieces

    def stream_text(self, system_prompt, text):
        self.turns.append(text)
        self.closed = False
        try:
            if self.failure:
                raise ReplyFailed(self.failure)
            yield from self.pieces
        finally:
            self.closed = True


def request(crisis: bool = False) -> TurnRequest:
    return TurnRequest(
        turn_id=7, system_prompt="SYSTEM", history=(MESSAGE,), entries=(THESIS,),
        crisis=crisis, today=date(2026, 11, 5), now=NOW, calibration=CAL,
    )


def worker(
    qtbot, *, replier=None, interpreter=None, embedder=None, ask_core=None
) -> ChatWorker:
    made = ChatWorker(
        replier or FakeReplier(), interpreter or FakeInterpreter(),
        embedder or FakeEmbedder(), ask_core=ask_core,
    )
    return made


def reply_request(turn: str = "", tools: bool = True, text: str = "") -> ReplyRequest:
    history = (MESSAGE,) if not text else (Message("m2", "c", USER, text, NOW),)
    return ReplyRequest(
        turn_id=1, system_prompt="SYSTEM", history=history, turn=turn,
        tools=tools, now=NOW, entries=(THESIS,), calibration=CAL,
    )


def collect(signal) -> list:
    """Each emission: its one argument, or a tuple of several."""
    caught: list = []
    signal.connect(lambda *args: caught.append(args[0] if len(args) == 1 else args))
    return caught


def test_prepare_full_path(qtbot) -> None:
    interpreter, embedder = FakeInterpreter(), FakeEmbedder()
    chat = worker(qtbot, interpreter=interpreter, embedder=embedder)
    caught = collect(chat.prepared)

    chat.prepare(request())

    (prepared,) = caught
    assert isinstance(prepared, Prepared)
    assert prepared.turn_id == 7
    assert [s.entry.id for s in prepared.recalled] == ["i1"]
    assert prepared.found.facts == ("Has a supervisor",)
    assert set(prepared.vectors) == {"Has a supervisor"}
    assert embedder.calls[0] == [MESSAGE.text]
    assert "- Is writing a thesis" in interpreter.turns[0]


def test_prepare_without_embeddings(qtbot) -> None:
    chat = worker(qtbot, embedder=FakeEmbedder(failing=True))
    caught = collect(chat.prepared)

    chat.prepare(request())

    (prepared,) = caught
    assert prepared.recalled[0].score == pytest.approx(0.8)
    assert prepared.found is not None
    assert prepared.vectors == {}


def test_prepare_interpret_failed(qtbot) -> None:
    chat = worker(qtbot, interpreter=FakeInterpreter(failing=True))
    caught = collect(chat.prepared)

    chat.prepare(request())

    assert caught[0].found is None


def test_prepare_bad_shape(qtbot) -> None:
    chat = worker(qtbot, interpreter=FakeInterpreter(answer={"importance": "high"}))
    caught = collect(chat.prepared)

    chat.prepare(request())

    assert caught[0].found is None


def test_prepare_crisis_does_not_interpret(qtbot) -> None:
    interpreter = FakeInterpreter()
    chat = worker(qtbot, interpreter=interpreter)
    caught = collect(chat.prepared)

    chat.prepare(request(crisis=True))

    assert caught[0].found is None
    assert interpreter.turns == []


def test_request_passes_turn(qtbot) -> None:
    replier = FakeReplier()
    chat = worker(qtbot, replier=replier)
    pieces, finished = collect(chat.chunk), collect(chat.finished)

    chat.request(reply_request("You remember:\n- A"))

    assert replier.turns == ["You remember:\n- A"]
    assert pieces == ["Hel", "lo"]
    assert finished == [Replied(1, "Hello")]


def test_request_failure(qtbot) -> None:
    chat = worker(qtbot, replier=FakeReplier(failure="Start it again."))
    failed = collect(chat.failed)

    chat.request(reply_request())

    assert failed == [(1, "Start it again.")]


def test_cancel_drops_the_reply(qtbot) -> None:
    chat = worker(qtbot)
    finished = collect(chat.finished)

    def cancel_after_first(piece: str) -> None:
        chat.cancel()

    chat.chunk.connect(cancel_after_first)
    chat.request(reply_request())

    assert finished == []


def test_cancel_before_request_starts_no_stream(qtbot) -> None:
    replier = FakeReplier()
    chat = worker(qtbot, replier=replier)
    finished, failed = collect(chat.finished), collect(chat.failed)
    chunks = collect(chat.chunk)
    chat.cancel()

    chat.request(reply_request())

    assert replier.turns == []
    assert (finished, failed, chunks) == ([], [], [])


def test_prepare_clears_cancel(qtbot) -> None:
    chat = worker(qtbot)
    finished = collect(chat.finished)
    chat.cancel()

    chat.prepare(request())
    chat.request(reply_request())

    assert [done.text for done in finished] == ["Hello"]


def test_embed_emits_pairs(qtbot) -> None:
    chat = worker(qtbot)
    caught = collect(chat.embedded)

    chat.embed([THESIS])

    assert caught == [[(THESIS, (1.0, 0.0))]]


def test_embed_failure_emits_nothing(qtbot) -> None:
    chat = worker(qtbot, embedder=FakeEmbedder(failing=True))
    caught = collect(chat.embedded)

    chat.embed([THESIS])

    assert caught == []


# ── summaries ────────────────────────────────────────────────────────────


def job(turn_id: int | None = None) -> SummaryJob:
    return SummaryJob("c", None, (MESSAGE,), 1, turn_id)


def test_summarize_emits_the_tidy_text(qtbot) -> None:
    chat = worker(qtbot, replier=FakeReplier(pieces=("They  met. ", "Then talked.")))
    caught = collect(chat.summarized)

    chat.summarize(job(turn_id=3))

    assert caught == [SummaryDone(job(turn_id=3), "They met. Then talked.")]


def test_background_summary_stops_on_cancel(qtbot) -> None:
    replier = FakeReplier(pieces=("They ", "met."))
    chat = worker(qtbot, replier=replier)
    caught = collect(chat.summarized)
    original = replier.stream_text

    def cancel_after_first(system_prompt, text):
        for n, piece in enumerate(original(system_prompt, text)):
            if n == 1:
                chat.cancel_summary()
            yield piece

    replier.stream_text = cancel_after_first
    chat.summarize(job())

    assert caught == []
    assert replier.closed


def test_background_skipped_if_flag_set(qtbot) -> None:
    replier = FakeReplier()
    chat = worker(qtbot, replier=replier)
    caught = collect(chat.summarized)
    chat.cancel_summary()

    chat.summarize(job())

    assert caught == []
    assert replier.turns == []


def test_sync_summary_ignores_send_flag(qtbot) -> None:
    chat = worker(qtbot, replier=FakeReplier(pieces=("They met.",)))
    caught = collect(chat.summarized)
    chat.cancel_summary()

    chat.summarize(job(turn_id=3))

    assert caught == [SummaryDone(job(turn_id=3), "They met.")]


def test_turn_summary_clears_stale_cancel(qtbot) -> None:
    chat = worker(qtbot, replier=FakeReplier(pieces=("They met.",)))
    caught = collect(chat.summarized)
    chat.cancel()

    chat.summarize(job(turn_id=3))

    assert caught == [SummaryDone(job(turn_id=3), "They met.")]


def test_cancel_stops_turn_summary(qtbot) -> None:
    replier = FakeReplier(pieces=("They ", "met."))
    chat = worker(qtbot, replier=replier)
    caught = collect(chat.summarized)
    original = replier.stream_text

    def cancel_after_first(system_prompt, text):
        for n, piece in enumerate(original(system_prompt, text)):
            if n == 1:
                chat.cancel()
            yield piece

    replier.stream_text = cancel_after_first
    chat.summarize(job(turn_id=3))

    assert caught == []
    assert replier.closed


def test_sync_summary_failure_emits_empty(qtbot) -> None:
    chat = worker(qtbot, replier=FakeReplier(failure="down"))
    caught = collect(chat.summarized)

    chat.summarize(job(turn_id=3))

    assert caught == [SummaryDone(job(turn_id=3), "")]


def test_background_failure_emits_nothing(qtbot) -> None:
    chat = worker(qtbot, replier=FakeReplier(failure="down"))
    caught = collect(chat.summarized)

    chat.summarize(job())

    assert caught == []


def test_prepare_clears_the_stop_flag(qtbot) -> None:
    chat = worker(qtbot, replier=FakeReplier(pieces=("They met.",)))
    caught = collect(chat.summarized)
    chat.cancel_summary()
    chat.prepare(request())

    chat.summarize(job())

    assert len(caught) == 1


# ── tools ────────────────────────────────────────────────────────────────


class ToolReplier(FakeReplier):
    """Calls each of ``calls`` through ``run_tool`` before answering."""

    def __init__(self, calls, pieces=("Done.",)) -> None:
        super().__init__(pieces=pieces)
        self.calls = calls
        self.answers: list[str] = []

    def stream_reply(self, system_prompt, history, turn, tools=(), run_tool=None):
        self.tools = tuple(tools)
        for call in self.calls:
            yield ToolStarted(call.name)
            self.answers.append(run_tool(call))
        yield from self.pieces


def test_tool_started_emits_label(qtbot) -> None:
    chat = worker(qtbot, replier=ToolReplier([ToolCall("date", {"op": "today"})]))
    labels = collect(chat.toolStarted)

    chat.request(reply_request())

    assert labels == ["checking the date"]


def test_results_reach_finished(qtbot) -> None:
    replier = ToolReplier([ToolCall("calculate", {"expression": "12*7"})])
    chat = worker(qtbot, replier=replier)
    finished = collect(chat.finished)

    chat.request(reply_request())

    assert finished == [
        Replied(1, "Done.", (ToolResult("calculate", "12*7 = 84"),))
    ]


def test_crisis_request_offers_no_tools(qtbot) -> None:
    replier = FakeReplier()
    chat = worker(qtbot, replier=replier)

    chat.request(reply_request(tools=False))

    assert replier.tools == ()


def test_ordinary_request_offers_every_tool(qtbot) -> None:
    replier = FakeReplier()
    chat = worker(qtbot, replier=replier)

    chat.request(reply_request())

    assert {s.name for s in replier.tools} == {s.name for s in catalog.SPECS}


def test_core_tool_waits_for_the_core(qtbot) -> None:
    def ask_core(call, now):
        answer = Future()
        answer.set_result("Feeling now: calm.")
        return answer

    replier = ToolReplier([ToolCall("why_i_feel")])
    chat = worker(qtbot, replier=replier, ask_core=ask_core)

    chat.request(reply_request())

    assert replier.answers == ["Feeling now: calm."]


def test_core_tool_timeout_sentence(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(chat_worker, "TOOL_SECONDS", 0.3)
    replier = ToolReplier([ToolCall("why_i_feel")])
    chat = worker(qtbot, replier=replier, ask_core=lambda call, now: Future())

    chat.request(reply_request())

    assert replier.answers == [tool_rules.TOOL_FAILED]


def test_cancel_stops_wait(qtbot) -> None:
    pending: list[Future] = []

    def ask_core(call, now):
        answer = Future()
        pending.append(answer)
        chat.cancel()
        return answer

    replier = ToolReplier([ToolCall("why_i_feel")])
    chat = worker(qtbot, replier=replier, ask_core=ask_core)
    finished = collect(chat.finished)

    chat.request(reply_request())

    assert pending[0].cancelled()
    assert finished == []


def test_open_refused_when_not_asked(qtbot) -> None:
    replier = ToolReplier([ToolCall("open_in_browser", {"search": "news"})])
    chat = worker(qtbot, replier=replier)
    opened = collect(chat.browserRequested)

    chat.request(reply_request(text="What's the news?"))

    assert replier.answers == [tool_rules.NOT_ASKED]
    assert opened == []


def test_open_when_asked(qtbot) -> None:
    replier = ToolReplier([ToolCall("open_in_browser", {"search": "cat food"})])
    chat = worker(qtbot, replier=replier)
    opened = collect(chat.browserRequested)

    chat.request(reply_request(text="Open a search for cat food"))

    assert opened == ["https://duckduckgo.com/?q=cat+food"]
    assert replier.answers == ["Opened a search for 'cat food' in the user's browser."]


def test_recall_memory_by_vector(qtbot) -> None:
    replier = ToolReplier([ToolCall("recall_memory", {"query": "thesis"})])
    chat = worker(qtbot, replier=replier)

    chat.request(reply_request())

    assert replier.answers == [
        "Stored lines: Is writing a thesis (told 5 November 2026)"
    ]


def test_recall_memory_embed_failure_sentence(qtbot) -> None:
    replier = ToolReplier([ToolCall("recall_memory", {"query": "thesis"})])
    chat = worker(qtbot, replier=replier, embedder=FakeEmbedder(failing=True))

    chat.request(reply_request())

    assert replier.answers == [memory_rules.UNSEARCHABLE]


def test_unknown_tool_sentence(qtbot) -> None:
    replier = ToolReplier([ToolCall("music")])
    chat = worker(qtbot, replier=replier)

    chat.request(reply_request())

    assert replier.answers == [tool_rules.TOOL_FAILED]



class FakeDictionary:
    def __init__(self, failing: bool = False) -> None:
        self.failing = failing
        self.asked: list[str] = []

    def senses(self, word):
        from src.domain.ports import DictionaryUnavailable, Sense

        self.asked.append(word)
        if self.failing:
            raise DictionaryUnavailable("The dictionary cannot be read.")
        return [Sense("noun", "the study of things")] if word == "study" else []


def test_define_word_finds_the_base_form(qtbot) -> None:
    replier = ToolReplier([ToolCall("define_word", {"word": "studies"})])
    chat = ChatWorker(FakeReplier(), FakeInterpreter(), FakeEmbedder(),
                      dictionary=FakeDictionary())
    chat._replier = replier

    chat.request(reply_request())

    assert replier.answers == ["study (noun): the study of things"]


def test_define_word_unknown(qtbot) -> None:
    replier = ToolReplier([ToolCall("define_word", {"word": "zyxq"})])
    chat = ChatWorker(replier, FakeInterpreter(), FakeEmbedder(),
                      dictionary=FakeDictionary())

    chat.request(reply_request())

    assert replier.answers == [
        "The dictionary on this machine has no entry for 'zyxq'."
    ]


def test_define_word_unavailable(qtbot) -> None:
    replier = ToolReplier([ToolCall("define_word", {"word": "cat"})])
    chat = ChatWorker(replier, FakeInterpreter(), FakeEmbedder(),
                      dictionary=FakeDictionary(failing=True))

    chat.request(reply_request())

    assert replier.answers == ["The dictionary cannot be read."]
