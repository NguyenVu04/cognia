"""The companion's replies, from a model running on this machine.

A LangGraph graph with one node. That looks like ceremony for a single call to
a model, and today it is — but it is the seam the rest of UC-09 needs. Memory
extraction (FR-14), the in-conversation adjustment (FR-15) and any tool the
companion is ever given are new nodes and edges here, not a rewrite of the call
site. The graph is deliberately stateless: the conversation lives in the store,
which is readable, rather than in a checkpointer, which would not be.

Nothing above ``infrastructure/`` knows this file exists. The application talks
to :class:`~src.core.ports.Replier`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, MessagesState, StateGraph

from src.core.models import Message
from src.core.ports import ReplyFailed


class OllamaAgent:
    """A :class:`~src.core.ports.Replier` backed by a local Ollama daemon."""

    def __init__(self, model: str, base_url: str) -> None:
        self._model = model
        self._base_url = base_url
        # reasoning=True lets the model think before it answers; the thinking
        # arrives separately from the answer (see _stream) and is dropped. The
        # design has nowhere to put a chain of thought, and the user asked not
        # to see one.
        self._llm = ChatOllama(model=model, base_url=base_url, reasoning=True)
        self._graph = self._build()

    def _build(self):
        def respond(state: MessagesState) -> dict:
            return {"messages": [self._llm.invoke(state["messages"])]}

        builder = StateGraph(MessagesState)
        builder.add_node("respond", respond)
        builder.add_edge(START, "respond")
        builder.add_edge("respond", END)
        return builder.compile()

    # ── port ──────────────────────────────────────────────────────────────

    def stream_reply(
        self, system_prompt: str, history: Sequence[Message]
    ) -> Iterator[str]:
        state = {"messages": self._to_langchain(system_prompt, history)}
        try:
            for chunk, _metadata in self._graph.stream(state, stream_mode="messages"):
                # The answer is in .content; the model's reasoning is in
                # additional_kwargs["reasoning_content"], which we never read.
                # Verified against langchain-ollama 1.1.0 with qwen3.5:2b.
                text = chunk.content
                if text and isinstance(text, str):
                    yield text
        except ReplyFailed:
            raise
        except Exception as error:  # noqa: BLE001 - every failure becomes one sentence
            raise ReplyFailed(self._explain(error)) from error

    # ── translation ───────────────────────────────────────────────────────

    @staticmethod
    def _to_langchain(system_prompt: str, history: Sequence[Message]) -> list:
        messages: list = [SystemMessage(system_prompt)]
        for message in history:
            messages.append(
                HumanMessage(message.text)
                if message.from_user
                else AIMessage(message.text)
            )
        return messages

    def _explain(self, error: Exception) -> str:
        """UC-09 E1: say plainly what happened and what would fix it."""
        detail = str(error).lower()
        if "not found" in detail or "try pulling" in detail:
            return (
                f"The model “{self._model}” isn’t installed. "
                f"Run “ollama pull {self._model}” and try again."
            )
        if any(
            word in detail
            for word in ("connect", "connection", "refused", "timed out", "timeout")
        ):
            return (
                f"I can’t reach Ollama at {self._base_url}. "
                "Start it with “ollama serve” and try again."
            )
        return f"I can’t reply just now — Ollama returned an error. {error}"
