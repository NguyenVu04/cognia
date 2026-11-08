"""Replies, interpretations and vectors from the llama-server processes.

The messages follow the layers: the system text, then the history, and layer 4
at the end of the last user message. The model's reasoning arrives apart from
the answer and is dropped.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping, Sequence

import httpx

from src.domain.conversation.models import Message
from src.domain.ports import EmbedFailed, InterpretFailed, ReplyFailed
from src.domain.tools.models import ToolCall, ToolSpec, ToolStarted
from src.infrastructure.ai.supervisor import (
    CHAT,
    EMBEDDING,
    Endpoint,
    ModelSupervisor,
    ModelUnavailable,
)

LOST = (
    "I lost the connection to the model on this machine. Try again; Cognia "
    "starts it again if it stopped."
)
REFUSED = "The model on this machine returned an error. Try again."
GARBLED = "The model on this machine sent an answer that could not be read."
RAMBLED = (
    "The model on this machine thought for too long and stopped. Try asking "
    "again."
)
TOO_LONG = (
    "This conversation is too long for the model on this machine. Start a new "
    "conversation with the + button; your remembered lines stay."
)

# What llama-server names an error for a prompt longer than its context.
_TOO_LONG_TYPE = "exceed_context_size_error"

# A reply can think for a while before its first word, and a CPU is slow.
_TIMEOUT = httpx.Timeout(300, connect=5)


class LlamaClient:
    """A :class:`~src.domain.ports.Replier`, an
    :class:`~src.domain.ports.Interpreter` and an
    :class:`~src.domain.ports.Embedder`.

    ``max_chars`` cuts each text before it is embedded, because the embedding
    model reads a limited number of tokens and refuses a longer text. A reply
    goes through the tool loop, where ``reply_max_tokens`` caps each model
    call; ``reply_http`` replaces its HTTP client in a test.
    ``interpret_max_tokens`` and ``summary_max_tokens`` cap an interpretation
    and a summary. ``None`` leaves each to the context.
    """

    def __init__(
        self,
        supervisor: ModelSupervisor,
        *,
        max_chars: int,
        reply_max_tokens: int | None = None,
        interpret_max_tokens: int | None = None,
        summary_max_tokens: int | None = None,
        http: httpx.Client | None = None,
        reply_http: object | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._max_chars = max_chars
        self._reply_max_tokens = reply_max_tokens
        self._interpret_max_tokens = interpret_max_tokens
        self._summary_max_tokens = summary_max_tokens
        self._http = http or httpx.Client(timeout=_TIMEOUT)
        self._reply_http = reply_http

    # ── Replier ───────────────────────────────────────────────────────────

    def stream_reply(
        self,
        system_prompt: str,
        history: Sequence[Message],
        turn: str,
        tools: Sequence[ToolSpec] = (),
        run_tool: Callable[[ToolCall], str] | None = None,
    ) -> Iterator[str | ToolStarted]:
        endpoint = self._endpoint(CHAT, ReplyFailed)
        from src.infrastructure.ai import tool_loop

        yield from tool_loop.stream(
            endpoint,
            messages(system_prompt, history, turn),
            tools,
            run_tool or _no_tool,
            max_tokens=self._reply_max_tokens,
            http_client=self._reply_http,
        )

    def stream_text(self, system_prompt: str, text: str) -> Iterator[str]:
        return self._stream(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ]
        )

    def _stream(self, sent: list[dict[str, str]]) -> Iterator[str]:
        """The answer's pieces. Closing the iterator closes the connection, and
        the server then stops generating."""
        endpoint = self._endpoint(CHAT, ReplyFailed)
        body = {"messages": sent, "stream": True}
        if self._summary_max_tokens is not None:
            body["max_tokens"] = self._summary_max_tokens
        stopped_early = (
            RAMBLED if self._summary_max_tokens is not None else TOO_LONG
        )
        try:
            with self._http.stream(
                "POST", _chat_url(endpoint), json=body, headers=_auth(endpoint)
            ) as response:
                if response.status_code != 200:
                    raise ReplyFailed(_refusal(response.read()))
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line.removeprefix("data: ")
                    if data == "[DONE]":
                        return
                    choice = json.loads(data)["choices"][0]
                    text = choice.get("delta", {}).get("content")
                    if text:
                        yield text
                    # The cap or the context stopped the answer mid-way.
                    if choice.get("finish_reason") == "length":
                        raise ReplyFailed(stopped_early)
        except httpx.HTTPError as error:
            raise ReplyFailed(LOST) from error
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ReplyFailed(GARBLED) from error

    # ── Interpreter ───────────────────────────────────────────────────────

    def interpret(
        self,
        system_prompt: str,
        history: Sequence[Message],
        turn: str,
        schema: Mapping[str, object],
    ) -> Mapping[str, object]:
        endpoint = self._endpoint(CHAT, InterpretFailed)
        body = {
            "messages": messages(system_prompt, history, turn),
            "stream": False,
            # The same message gives the same reading, so a replay of the
            # feeling it caused is explainable.
            "temperature": 0,
            # This build applies a schema only in the OpenAI form.
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "interpretation", "schema": dict(schema)},
            },
        }
        if self._interpret_max_tokens is not None:
            body["max_tokens"] = self._interpret_max_tokens
        try:
            response = self._http.post(
                _chat_url(endpoint), json=body, headers=_auth(endpoint)
            )
        except httpx.HTTPError as error:
            raise InterpretFailed(LOST) from error
        if response.status_code != 200:
            raise InterpretFailed(_refusal(response.content))
        try:
            choice = response.json()["choices"][0]
            if choice.get("finish_reason") == "length":
                raise InterpretFailed(
                    RAMBLED if self._interpret_max_tokens is not None else TOO_LONG
                )
            answer = json.loads(choice["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise InterpretFailed(GARBLED) from error
        if not isinstance(answer, dict):
            raise InterpretFailed(GARBLED)
        return answer

    # ── Embedder ──────────────────────────────────────────────────────────

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []
        endpoint = self._endpoint(EMBEDDING, EmbedFailed)
        body = {"input": [text[: self._max_chars] for text in texts]}
        try:
            response = self._http.post(
                f"{endpoint.base_url}/v1/embeddings", json=body, headers=_auth(endpoint)
            )
        except httpx.HTTPError as error:
            raise EmbedFailed(LOST) from error
        if response.status_code != 200:
            raise EmbedFailed(REFUSED)
        try:
            rows = sorted(response.json()["data"], key=lambda row: row["index"])
            vectors = [tuple(float(x) for x in row["embedding"]) for row in rows]
        except (ValueError, KeyError, TypeError) as error:
            raise EmbedFailed(GARBLED) from error
        if len(vectors) != len(texts):
            raise EmbedFailed(GARBLED)
        return vectors

    def close(self) -> None:
        self._http.close()

    def _endpoint(self, server: str, failure: type[Exception]) -> Endpoint:
        try:
            return self._supervisor.endpoint(server)
        except ModelUnavailable as error:
            raise failure(str(error)) from error


def messages(
    system_prompt: str, history: Sequence[Message], turn: str
) -> list[dict[str, str]]:
    """The request messages. ``turn`` joins the last user message, after a
    blank line. Two messages in a row from the same side join the same way."""
    built = [{"role": "system", "content": system_prompt}]
    for m in history:
        role = "user" if m.from_user else "assistant"
        # The chat template refuses two messages in a row from one side, which
        # a reply that failed leaves behind.
        if len(built) > 1 and built[-1]["role"] == role:
            built[-1]["content"] += f"\n\n{m.text}"
        else:
            built.append({"role": role, "content": m.text})
    if turn:
        last_user = next(
            (m for m in reversed(built) if m["role"] == "user"), None
        )
        if last_user is not None:
            last_user["content"] += f"\n\n{turn}"
    return built


def _no_tool(call: ToolCall) -> str:
    raise ValueError(f"No tool was offered, yet the model called {call.name!r}.")


def _refusal(body: bytes) -> str:
    """The sentence for an answer that is not 200: too long, or anything else."""
    try:
        kind = json.loads(body)["error"]["type"]
    except (ValueError, KeyError, TypeError):
        return REFUSED
    return TOO_LONG if kind == _TOO_LONG_TYPE else REFUSED


def _chat_url(endpoint: Endpoint) -> str:
    return f"{endpoint.base_url}/v1/chat/completions"


def _auth(endpoint: Endpoint) -> dict[str, str]:
    return {"Authorization": f"Bearer {endpoint.api_key}"}
