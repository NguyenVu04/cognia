import json
from datetime import datetime, timezone

import httpx
import pytest

from src.domain.conversation.models import COMPANION, USER, Message
from src.domain.ports import EmbedFailed, InterpretFailed, ReplyFailed
from src.infrastructure.ai.llama_client import (
    GARBLED,
    LOST,
    REFUSED,
    LlamaClient,
    messages,
)
from src.infrastructure.ai.supervisor import Endpoint, ModelUnavailable

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
HISTORY = [
    Message("1", "c", USER, "Hi", NOW),
    Message("2", "c", COMPANION, "Hello.", NOW),
    Message("3", "c", USER, "I sent chapter 3!", NOW),
]


class FakeSupervisor:
    def __init__(self, failure: str | None = None) -> None:
        self.failure = failure
        self.asked: list[str] = []

    def endpoint(self, server: str) -> Endpoint:
        self.asked.append(server)
        if self.failure:
            raise ModelUnavailable(self.failure)
        return Endpoint("http://127.0.0.1:9001", "key-1")


def sse(*chunks: dict) -> bytes:
    lines = [f"data: {json.dumps(chunk)}\n\n" for chunk in chunks]
    return ("".join(lines) + "data: [DONE]\n\n").encode()


def delta(**fields) -> dict:
    return {"choices": [{"index": 0, "delta": fields}]}


def client(handler, supervisor=None) -> tuple[LlamaClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(record))
    return LlamaClient(supervisor or FakeSupervisor(), max_chars=1200, http=http), seen


# ── messages ─────────────────────────────────────────────────────────────


def test_messages_put_layer_4_on_last_user_message() -> None:
    built = messages("SYSTEM", HISTORY, "You remember:\n- Is writing a thesis")

    assert [m["role"] for m in built] == ["system", "user", "assistant", "user"]
    assert built[0]["content"] == "SYSTEM"
    assert built[-1]["content"] == (
        "I sent chapter 3!\n\nYou remember:\n- Is writing a thesis"
    )
    assert built[1]["content"] == "Hi"


def test_messages_empty_turn_unchanged() -> None:
    assert messages("SYSTEM", HISTORY, "")[-1]["content"] == "I sent chapter 3!"


# ── stream_reply ─────────────────────────────────────────────────────────


def test_stream_yields_content_and_drops_reasoning() -> None:
    body = sse(
        delta(role="assistant", content=None),
        delta(reasoning_content="They sound proud."),
        delta(content="Hel"),
        delta(content="lo"),
    )
    llama, seen = client(lambda r: httpx.Response(200, content=body))

    pieces = list(llama.stream_reply("SYSTEM", HISTORY, "Be brief."))

    assert pieces == ["Hel", "lo"]
    request = seen[0]
    assert request.url == "http://127.0.0.1:9001/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer key-1"
    sent = json.loads(request.content)
    assert sent["stream"] is True
    assert sent["messages"][-1]["content"].endswith("\n\nBe brief.")


def test_stream_connection_error() -> None:
    def refuse(request):
        raise httpx.ConnectError("refused")

    llama, _ = client(refuse)

    with pytest.raises(ReplyFailed, match=LOST):
        list(llama.stream_reply("SYSTEM", HISTORY, ""))


def test_stream_model_unavailable_keeps_sentence() -> None:
    llama, seen = client(lambda r: httpx.Response(200), FakeSupervisor("Reinstall."))

    with pytest.raises(ReplyFailed, match="Reinstall."):
        list(llama.stream_reply("SYSTEM", HISTORY, ""))
    assert seen == []


def test_stream_http_500() -> None:
    llama, _ = client(lambda r: httpx.Response(500, content=b"{}"))

    with pytest.raises(ReplyFailed, match=REFUSED):
        list(llama.stream_reply("SYSTEM", HISTORY, ""))


def test_stream_garbled() -> None:
    llama, _ = client(lambda r: httpx.Response(200, content=b"data: {not json\n\n"))

    with pytest.raises(ReplyFailed, match=GARBLED):
        list(llama.stream_reply("SYSTEM", HISTORY, ""))


# ── interpret ────────────────────────────────────────────────────────────


def answer(content: str) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": content}}]}
    )


def test_interpret_sends_schema_and_returns_object() -> None:
    schema = {"type": "object", "properties": {"importance": {"type": "integer"}}}
    llama, seen = client(lambda r: answer('{"importance": 8}'))

    result = llama.interpret("SYSTEM", HISTORY, "Answer as JSON.", schema)

    assert result == {"importance": 8}
    sent = json.loads(seen[0].content)
    assert sent["stream"] is False
    assert sent["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "interpretation", "schema": schema},
    }
    assert sent["messages"][-1]["content"].endswith("\n\nAnswer as JSON.")


def test_interpret_not_json() -> None:
    llama, _ = client(lambda r: answer("I am pleased."))

    with pytest.raises(InterpretFailed, match=GARBLED):
        llama.interpret("SYSTEM", HISTORY, "", {})


def test_interpret_not_an_object() -> None:
    llama, _ = client(lambda r: answer("[1, 2]"))

    with pytest.raises(InterpretFailed, match=GARBLED):
        llama.interpret("SYSTEM", HISTORY, "", {})


def test_interpret_connection_error() -> None:
    def refuse(request):
        raise httpx.ConnectError("refused")

    llama, _ = client(refuse)

    with pytest.raises(InterpretFailed, match=LOST):
        llama.interpret("SYSTEM", HISTORY, "", {})


def test_interpret_model_unavailable() -> None:
    llama, _ = client(lambda r: answer("{}"), FakeSupervisor("Reinstall."))

    with pytest.raises(InterpretFailed, match="Reinstall."):
        llama.interpret("SYSTEM", HISTORY, "", {})


# ── embed ────────────────────────────────────────────────────────────────


def vectors(*rows: tuple[int, list[float]]) -> httpx.Response:
    data = [{"object": "embedding", "index": i, "embedding": v} for i, v in rows]
    return httpx.Response(200, json={"object": "list", "data": data})


def test_embed_keeps_input_order() -> None:
    supervisor = FakeSupervisor()
    llama, seen = client(
        lambda r: vectors((1, [0.0, 1.0]), (0, [1.0, 0.0])), supervisor
    )

    result = llama.embed(["first", "second"])

    assert result == [(1.0, 0.0), (0.0, 1.0)]
    assert seen[0].url == "http://127.0.0.1:9001/v1/embeddings"
    assert supervisor.asked == ["embedding"]


def test_embed_cuts_long_text() -> None:
    llama, seen = client(lambda r: vectors((0, [1.0])))

    llama.embed(["x" * 5000])

    assert json.loads(seen[0].content)["input"] == ["x" * 1200]


def test_embed_nothing() -> None:
    llama, seen = client(lambda r: vectors())

    assert llama.embed([]) == []
    assert seen == []


def test_embed_wrong_count() -> None:
    llama, _ = client(lambda r: vectors((0, [1.0])))

    with pytest.raises(EmbedFailed, match=GARBLED):
        llama.embed(["a", "b"])


def test_embed_error() -> None:
    llama, _ = client(lambda r: httpx.Response(500, json={"error": {}}))

    with pytest.raises(EmbedFailed, match=REFUSED):
        llama.embed(["a"])
