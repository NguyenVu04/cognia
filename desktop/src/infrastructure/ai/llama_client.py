"""Replies, interpretations and vectors from the llama-server processes.

The messages follow the layers: the system text, then the history, and layer 4
at the end of the last user message. The model's reasoning arrives apart from
the answer and is dropped.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence

import httpx

from src.domain.conversation.models import Message
from src.domain.ports import EmbedFailed, InterpretFailed, ReplyFailed
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

# A reply can think for a while before its first word, and a CPU is slow.
_TIMEOUT = httpx.Timeout(300, connect=5)


class LlamaClient:
    """A :class:`~src.domain.ports.Replier`, an
    :class:`~src.domain.ports.Interpreter` and an
    :class:`~src.domain.ports.Embedder`.

    ``max_chars`` cuts each text before it is embedded, because the embedding
    model reads a limited number of tokens and refuses a longer text.
    """

    def __init__(
        self,
        supervisor: ModelSupervisor,
        *,
        max_chars: int,
        http: httpx.Client | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._max_chars = max_chars
        self._http = http or httpx.Client(timeout=_TIMEOUT)

    # ── Replier ───────────────────────────────────────────────────────────

    def stream_reply(
        self, system_prompt: str, history: Sequence[Message], turn: str
    ) -> Iterator[str]:
        endpoint = self._endpoint(CHAT, ReplyFailed)
        body = {"messages": messages(system_prompt, history, turn), "stream": True}
        try:
            with self._http.stream(
                "POST", _chat_url(endpoint), json=body, headers=_auth(endpoint)
            ) as response:
                if response.status_code != 200:
                    raise ReplyFailed(REFUSED)
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line.removeprefix("data: ")
                    if data == "[DONE]":
                        return
                    piece = json.loads(data)["choices"][0].get("delta", {})
                    text = piece.get("content")
                    if text:
                        yield text
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
            # This build applies a schema only in the OpenAI form.
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "interpretation", "schema": dict(schema)},
            },
        }
        try:
            response = self._http.post(
                _chat_url(endpoint), json=body, headers=_auth(endpoint)
            )
        except httpx.HTTPError as error:
            raise InterpretFailed(LOST) from error
        if response.status_code != 200:
            raise InterpretFailed(REFUSED)
        try:
            answer = json.loads(response.json()["choices"][0]["message"]["content"])
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
    blank line."""
    built = [{"role": "system", "content": system_prompt}]
    built += [
        {"role": "user" if m.from_user else "assistant", "content": m.text}
        for m in history
    ]
    if turn:
        last_user = next(
            (m for m in reversed(built) if m["role"] == "user"), None
        )
        if last_user is not None:
            last_user["content"] += f"\n\n{turn}"
    return built


def _chat_url(endpoint: Endpoint) -> str:
    return f"{endpoint.base_url}/v1/chat/completions"


def _auth(endpoint: Endpoint) -> dict[str, str]:
    return {"Authorization": f"Bearer {endpoint.api_key}"}
