import json
import os

import httpx2
import pytest

from src.domain.ports import ReplyFailed
from src.domain.tools.catalog import TOOL_ROUNDS, spec
from src.domain.tools.models import ToolCall, ToolStarted
from src.infrastructure.ai import tool_loop
from src.infrastructure.ai.llama_client import LOST, RAMBLED, TOO_LONG
from src.infrastructure.ai.supervisor import Endpoint

ENDPOINT = Endpoint("http://127.0.0.1:9001", "key-1")
SENT = [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "hi"}]
CALCULATE = spec("calculate")
OVERFLOW = {
    "error": {
        "code": 400,
        "message": "request (21727 tokens) exceeds the available context size",
        "type": "exceed_context_size_error",
    }
}


def chunk(finish: str | None = None, **delta) -> dict:
    return {
        "id": "c1", "object": "chat.completion.chunk", "created": 1, "model": "chat",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def sse(*chunks: dict) -> httpx2.Response:
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx2.Response(
        200, content=body.encode(), headers={"content-type": "text/event-stream"}
    )


def text(*pieces: str) -> httpx2.Response:
    return sse(
        chunk(role="assistant", content=""),
        *(chunk(content=p) for p in pieces),
        chunk(finish="stop"),
    )


def tool_call(name: str, arguments: dict, call_id: str = "call1") -> httpx2.Response:
    call = {
        "index": 0, "id": call_id, "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }
    return sse(
        chunk(role="assistant", content=None, tool_calls=[call]),
        chunk(finish="tool_calls"),
    )


def run(answers, tools=(), run_tool=None, max_tokens=None):
    """Every piece the loop yields, and every request body it sent."""
    seen: list[dict] = []
    queue = list(answers)

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append({"url": str(request.url), "body": json.loads(request.content)})
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        return answer(request) if callable(answer) else answer

    client = httpx2.Client(transport=httpx2.MockTransport(handle))
    pieces = list(
        tool_loop.stream(
            ENDPOINT, SENT, tools, run_tool or (lambda call: "done"),
            max_tokens=max_tokens, http_client=client,
        )
    )
    return pieces, seen


def test_tracing_off() -> None:
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_no_tools_streams_text() -> None:
    pieces, seen = run([text("Hel", "lo")])

    assert pieces == ["Hel", "lo"]
    assert "tools" not in seen[0]["body"]
    assert seen[0]["url"] == "http://127.0.0.1:9001/v1/chat/completions"


def test_reasoning_not_in_pieces() -> None:
    answer = sse(
        chunk(role="assistant", content=""),
        chunk(reasoning_content="They sound proud."),
        chunk(content="Well done."),
        chunk(finish="stop"),
    )

    pieces, _ = run([answer])

    assert pieces == ["Well done."]


def test_tool_started_before_run_then_answer() -> None:
    order: list[object] = []

    def run_tool(call: ToolCall) -> str:
        order.append(call)
        return "12*7 = 84"

    pieces, seen = run(
        [tool_call("calculate", {"expression": "12*7"}), text("It's 84.")],
        tools=(CALCULATE,),
        run_tool=run_tool,
    )

    assert pieces == [ToolStarted("calculate"), "It's 84."]
    assert order == [ToolCall("calculate", {"expression": "12*7"})]
    second = seen[1]["body"]["messages"]
    assert second[-1]["role"] == "tool"
    assert second[-1]["content"] == "12*7 = 84"
    assert second[-1]["tool_call_id"] == "call1"


def test_fourth_round_has_no_tools() -> None:
    def answer(request: httpx2.Request) -> httpx2.Response:
        if "tools" in json.loads(request.content):
            return tool_call("calculate", {"expression": "1+1"})
        return text("Enough sums.")

    pieces, seen = run([answer], tools=(CALCULATE,))

    assert pieces[-1] == "Enough sums."
    assert pieces.count(ToolStarted("calculate")) == TOOL_ROUNDS
    assert len(seen) == TOOL_ROUNDS + 1
    assert "tools" not in seen[-1]["body"]


def test_length_is_too_long() -> None:
    answer = sse(chunk(role="assistant", content="Once"), chunk(finish="length"))

    with pytest.raises(ReplyFailed) as caught:
        run([answer])
    assert str(caught.value) == TOO_LONG


def test_stream_sends_max_tokens() -> None:
    _, seen = run([text("Hi")], max_tokens=900)

    # LangChain sends the newer OpenAI name, which llama-server also reads.
    assert seen[0]["body"]["max_completion_tokens"] == 900


def test_stream_omits_max_tokens_when_none() -> None:
    _, seen = run([text("Hi")])

    assert "max_tokens" not in seen[0]["body"]
    assert "max_completion_tokens" not in seen[0]["body"]


def test_stream_length_with_cap_is_rambled() -> None:
    answer = sse(chunk(role="assistant", content="Once"), chunk(finish="length"))

    with pytest.raises(ReplyFailed) as caught:
        run([answer], max_tokens=900)
    assert str(caught.value) == RAMBLED


def test_overflow_400_is_too_long() -> None:
    with pytest.raises(ReplyFailed) as caught:
        run([httpx2.Response(400, json=OVERFLOW)])
    assert str(caught.value) == TOO_LONG


def test_connect_error_is_lost() -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    with pytest.raises(ReplyFailed) as caught:
        run([refuse])
    assert str(caught.value) == LOST
