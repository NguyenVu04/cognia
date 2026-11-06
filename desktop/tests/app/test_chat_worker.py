import math
from datetime import date, datetime, timezone

import pytest

from src.app.chat_worker import ChatWorker, Prepared, TurnRequest
from src.domain.conversation.models import USER, Message
from src.domain.memory.models import TOLD, Calibration, MemoryItem
from src.domain.ports import EmbedFailed, InterpretFailed, ReplyFailed

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

    def stream_reply(self, system_prompt, history, turn):
        self.turns.append(turn)
        if self.failure:
            raise ReplyFailed(self.failure)
        yield from self.pieces


def request(crisis: bool = False) -> TurnRequest:
    return TurnRequest(
        turn_id=7, system_prompt="SYSTEM", history=(MESSAGE,), entries=(THESIS,),
        crisis=crisis, today=date(2026, 11, 5), now=NOW, calibration=CAL,
    )


def worker(qtbot, *, replier=None, interpreter=None, embedder=None) -> ChatWorker:
    made = ChatWorker(
        replier or FakeReplier(), interpreter or FakeInterpreter(),
        embedder or FakeEmbedder(),
    )
    return made


def collect(signal) -> list:
    caught: list = []
    signal.connect(caught.append)
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

    chat.request("SYSTEM", [MESSAGE], "You remember:\n- A")

    assert replier.turns == ["You remember:\n- A"]
    assert pieces == ["Hel", "lo"]
    assert finished == ["Hello"]


def test_request_failure(qtbot) -> None:
    chat = worker(qtbot, replier=FakeReplier(failure="Start it again."))
    failed = collect(chat.failed)

    chat.request("SYSTEM", [MESSAGE], "")

    assert failed == ["Start it again."]


def test_cancel_drops_the_reply(qtbot) -> None:
    chat = worker(qtbot)
    finished = collect(chat.finished)

    def cancel_after_first(piece: str) -> None:
        chat.cancel()

    chat.chunk.connect(cancel_after_first)
    chat.request("SYSTEM", [MESSAGE], "")

    assert finished == []


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
