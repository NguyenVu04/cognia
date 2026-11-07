"""One reply as a LangGraph loop: the model may call tools, then answers.

The graph runs one turn only and owns no order of events: a tool that needs the
core's data asks through ``run_tool``, which the caller provides. After
``TOOL_ROUNDS`` rounds of tool calls the model is asked again with no tools, so
it must answer. A turn with no tools is the same graph with the model alone.

LangChain and LangGraph appear nowhere else in Cognia. Importing them takes
seconds, so this module is imported on the model thread after the window shows.
"""

import os

# LangChain can send traces to LangSmith; Cognia sends nothing off the machine.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ.pop("LANGCHAIN_TRACING_V2", None)

from collections.abc import Callable, Iterator, Sequence  # noqa: E402

import openai  # noqa: E402
from langchain_core.messages import AIMessageChunk, ToolMessage  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langgraph.config import get_stream_writer  # noqa: E402
from langgraph.graph import END, START, MessagesState, StateGraph  # noqa: E402

from src.domain.ports import ReplyFailed  # noqa: E402
from src.domain.tools.catalog import TOOL_ROUNDS  # noqa: E402
from src.domain.tools.models import ToolCall, ToolSpec, ToolStarted  # noqa: E402
from src.infrastructure.ai.llama_client import (  # noqa: E402
    GARBLED,
    LOST,
    RAMBLED,
    REFUSED,
    TOO_LONG,
)
from src.infrastructure.ai.supervisor import Endpoint  # noqa: E402

# A reply can think for a while before its first word, and a CPU is slow.
_TIMEOUT_SECONDS = 300
# What llama-server names an error for a prompt longer than its context.
_TOO_LONG_TYPE = "exceed_context_size_error"


class _State(MessagesState):
    rounds: int


def stream(
    endpoint: Endpoint,
    sent: list[dict[str, str]],
    tools: Sequence[ToolSpec],
    run_tool: Callable[[ToolCall], str],
    *,
    max_tokens: int | None = None,
    http_client: object | None = None,
) -> Iterator[str | ToolStarted]:
    """The pieces of the answer to ``sent``, and a :class:`ToolStarted` before
    each tool runs. ``max_tokens`` caps each model call, reasoning included, and
    ``None`` leaves it to the context. Raises :class:`ReplyFailed` with a
    sentence for the user."""
    # A reasoning model can think in circles until the context is full.
    stopped_early = RAMBLED if max_tokens is not None else TOO_LONG
    model = ChatOpenAI(
        base_url=f"{endpoint.base_url}/v1",
        api_key=endpoint.api_key,
        model="chat",
        max_retries=0,
        streaming=True,
        max_tokens=max_tokens,
        request_timeout=_TIMEOUT_SECONDS,
        http_client=http_client,
    )
    schemas = [_schema(spec) for spec in tools]
    with_tools = model.bind_tools(schemas) if schemas else model

    def answer(state: _State) -> dict:
        chosen = with_tools if state["rounds"] < TOOL_ROUNDS else model
        return {"messages": [chosen.invoke(state["messages"])]}

    def route(state: _State) -> str:
        calls = getattr(state["messages"][-1], "tool_calls", None)
        return "tools" if schemas and calls else END

    def call_tools(state: _State) -> dict:
        write = get_stream_writer()
        results = []
        for call in state["messages"][-1].tool_calls:
            write(ToolStarted(call["name"]))
            text = run_tool(ToolCall(call["name"], call.get("args") or {}))
            results.append(
                ToolMessage(content=text, tool_call_id=call["id"], name=call["name"])
            )
        return {"messages": results, "rounds": state["rounds"] + 1}

    graph = StateGraph(_State)
    graph.add_node("model", answer)
    graph.add_node("tools", call_tools)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", route)
    graph.add_edge("tools", "model")
    app = graph.compile()

    try:
        for mode, chunk in app.stream(
            {"messages": sent, "rounds": 0},
            stream_mode=["messages", "custom"],
            config={"recursion_limit": 2 * TOOL_ROUNDS + 4},
        ):
            if mode == "custom":
                yield chunk
                continue
            message, meta = chunk
            if meta.get("langgraph_node") != "model":
                continue
            if not isinstance(message, AIMessageChunk):
                continue
            if isinstance(message.content, str) and message.content:
                yield message.content
            # The cap or the context stopped the answer mid-way.
            if message.response_metadata.get("finish_reason") == "length":
                raise ReplyFailed(stopped_early)
    except openai.APIConnectionError as error:
        raise ReplyFailed(LOST) from error
    except openai.APIStatusError as error:
        too_long = _TOO_LONG_TYPE in str(error.body)
        raise ReplyFailed(TOO_LONG if too_long else REFUSED) from error
    except (
        openai.APIResponseValidationError, ValueError, KeyError, TypeError
    ) as error:
        raise ReplyFailed(GARBLED) from error


def _schema(spec: ToolSpec) -> dict:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": dict(spec.parameters),
        },
    }
