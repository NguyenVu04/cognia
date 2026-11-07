import json
from datetime import datetime, timezone

import httpx
import pytest

from src.domain.conversation.models import COMPANION, USER, Message
from src.domain.ports import EmbedFailed, InterpretFailed, ReplyFailed
from src.infrastructure.ai.llama_client import (
    GARBLED,
    LOST,
    RAMBLED,
    REFUSED,
    TOO_LONG,
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


def client(
    handler, supervisor=None, **caps
) -> tuple[LlamaClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(record))
    llama = LlamaClient(
        supervisor or FakeSupervisor(), max_chars=1200, http=http, **caps
    )
    return llama, seen


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


def test_messages_join_two_user_messages_in_a_row() -> None:
    history = [*HISTORY, Message("4", "c", USER, "Are you there?", NOW)]

    built = messages("SYSTEM", history, "Layer 4.")

    assert [m["role"] for m in built] == ["system", "user", "assistant", "user"]
    assert built[-1]["content"] == "I sent chapter 3!\n\nAre you there?\n\nLayer 4."


def test_messages_join_two_companion_messages_in_a_row() -> None:
    history = [
        Message("1", "c", USER, "Hi", NOW),
        Message("2", "c", COMPANION, "Hello.", NOW),
        Message("3", "c", COMPANION, "Still here.", NOW),
    ]

    built = messages("SYSTEM", history, "")

    assert [m["content"] for m in built] == ["SYSTEM", "Hi", "Hello.\n\nStill here."]


# ── the httpx stream (stream_text) ───────────────────────────────────────
# A reply goes through the tool loop; its tests are in test_tool_loop.py.


def test_stream_yields_content_and_drops_reasoning() -> None:
    body = sse(
        delta(role="assistant", content=None),
        delta(reasoning_content="They sound proud."),
        delta(content="Hel"),
        delta(content="lo"),
    )
    llama, seen = client(lambda r: httpx.Response(200, content=body))

    pieces = list(llama.stream_text("SYSTEM", "Be brief."))

    assert pieces == ["Hel", "lo"]
    request = seen[0]
    assert request.url == "http://127.0.0.1:9001/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer key-1"
    sent = json.loads(request.content)
    assert sent["stream"] is True
    assert sent["messages"][-1]["content"] == "Be brief."


def test_stream_connection_error() -> None:
    def refuse(request):
        raise httpx.ConnectError("refused")

    llama, _ = client(refuse)

    with pytest.raises(ReplyFailed, match=LOST):
        list(llama.stream_text("SYSTEM", "hi"))


def test_reply_model_unavailable_keeps_sentence() -> None:
    llama, _ = client(lambda r: httpx.Response(200), FakeSupervisor("Reinstall."))

    with pytest.raises(ReplyFailed, match="Reinstall."):
        list(llama.stream_reply("SYSTEM", HISTORY, ""))


def test_stream_model_unavailable_keeps_sentence() -> None:
    llama, seen = client(lambda r: httpx.Response(200), FakeSupervisor("Reinstall."))

    with pytest.raises(ReplyFailed, match="Reinstall."):
        list(llama.stream_text("SYSTEM", "hi"))
    assert seen == []


def test_stream_http_500() -> None:
    llama, _ = client(lambda r: httpx.Response(500, content=b"{}"))

    with pytest.raises(ReplyFailed, match=REFUSED):
        list(llama.stream_text("SYSTEM", "hi"))


def test_stream_garbled() -> None:
    llama, _ = client(lambda r: httpx.Response(200, content=b"data: {not json\n\n"))

    with pytest.raises(ReplyFailed, match=GARBLED):
        list(llama.stream_text("SYSTEM", "hi"))


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
    assert sent["temperature"] == 0
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


# ── too long, and text with no history ──────────────────────────────────

# The body llama-server b12121 sent for a prompt over its context.
OVERFLOW = {
    "error": {
        "code": 400,
        "message": "request (21727 tokens) exceeds the available context size "
        "(8192 tokens), try increasing it",
        "type": "exceed_context_size_error",
        "n_prompt_tokens": 21727,
        "n_ctx": 8192,
    }
}


def finish(reason: str) -> dict:
    return {"choices": [{"index": 0, "delta": {}, "finish_reason": reason}]}


def test_overflow_status_is_too_long() -> None:
    llama, _ = client(lambda r: httpx.Response(400, json=OVERFLOW))

    with pytest.raises(ReplyFailed, match="too long"):
        list(llama.stream_text("SYSTEM", "hi"))


def test_other_400_is_refused() -> None:
    llama, _ = client(lambda r: httpx.Response(400, json={"error": {"type": "x"}}))

    with pytest.raises(ReplyFailed) as caught:
        list(llama.stream_text("SYSTEM", "hi"))
    assert str(caught.value) == REFUSED


def test_finish_length_is_too_long() -> None:
    body = sse(delta(content="Once"), finish("length"))
    llama, _ = client(lambda r: httpx.Response(200, content=body))

    with pytest.raises(ReplyFailed) as caught:
        list(llama.stream_text("SYSTEM", "hi"))
    assert str(caught.value) == TOO_LONG


def test_finish_stop_is_fine() -> None:
    body = sse(delta(content="Done."), finish("stop"))
    llama, _ = client(lambda r: httpx.Response(200, content=body))

    assert list(llama.stream_text("SYSTEM", "hi")) == ["Done."]


def test_interpret_overflow_is_too_long() -> None:
    llama, _ = client(lambda r: httpx.Response(400, json=OVERFLOW))

    with pytest.raises(InterpretFailed) as caught:
        llama.interpret("SYSTEM", HISTORY, "Answer.", {"type": "object"})
    assert str(caught.value) == TOO_LONG


def test_stream_text_sends_system_and_text() -> None:
    body = sse(delta(content="ok"))
    llama, seen = client(lambda r: httpx.Response(200, content=body))

    assert list(llama.stream_text("SUMMARIZE", "Messages:\nUser: hi")) == ["ok"]
    sent = json.loads(seen[0].content)["messages"]
    assert sent == [
        {"role": "system", "content": "SUMMARIZE"},
        {"role": "user", "content": "Messages:\nUser: hi"},
    ]


# ── token caps ──────────────────────────────────────────────────────────────


def cut_off(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{
        "finish_reason": "length",
        "message": {"role": "assistant", "content": content}}]})


def test_interpret_sends_max_tokens() -> None:
    llama, seen = client(lambda r: answer("{}"), interpret_max_tokens=256)

    llama.interpret("SYSTEM", HISTORY, "Answer.", {"type": "object"})

    assert json.loads(seen[0].content)["max_tokens"] == 256


def test_interpret_without_cap_sends_none() -> None:
    llama, seen = client(lambda r: answer("{}"))

    llama.interpret("SYSTEM", HISTORY, "Answer.", {"type": "object"})

    assert "max_tokens" not in json.loads(seen[0].content)


def test_interpret_cap_reached_is_rambled() -> None:
    llama, _ = client(lambda r: cut_off('{"facts": ["a'), interpret_max_tokens=256)

    with pytest.raises(InterpretFailed) as caught:
        llama.interpret("SYSTEM", HISTORY, "Answer.", {"type": "object"})
    assert str(caught.value) == RAMBLED


def test_interpret_context_full_is_too_long() -> None:
    llama, _ = client(lambda r: cut_off('{"facts": ["a'))

    with pytest.raises(InterpretFailed) as caught:
        llama.interpret("SYSTEM", HISTORY, "Answer.", {"type": "object"})
    assert str(caught.value) == TOO_LONG


def test_stream_text_sends_max_tokens() -> None:
    body = sse(delta(content="ok"))
    llama, seen = client(lambda r: httpx.Response(200, content=body),
                         summary_max_tokens=1024)

    list(llama.stream_text("SUMMARIZE", "Messages:\nUser: hi"))

    assert json.loads(seen[0].content)["max_tokens"] == 1024


def test_stream_text_cap_reached_is_rambled() -> None:
    body = sse(delta(content="Once"), finish("length"))
    llama, _ = client(lambda r: httpx.Response(200, content=body),
                      summary_max_tokens=1024)

    with pytest.raises(ReplyFailed) as caught:
        list(llama.stream_text("SYSTEM", "hi"))
    assert str(caught.value) == RAMBLED
