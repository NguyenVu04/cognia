"""The prompt of an example as the application sends it, and the answer it
teaches.

Every text comes from the application's own rules, so the prompt matches what
``core_host`` and ``chat_worker`` build. The time of a turn is noon UTC on the
example's day.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import cache

from finetuning.examples import Example, Turn
from src.domain.awareness import rules as awareness_rules
from src.domain.awareness.models import DeskTime
from src.domain.character.models import Template
from src.domain.companion import rules as companion_rules
from src.domain.conversation import rules as conversation_rules
from src.domain.conversation.models import COMPANION, USER, Message
from src.domain.events.models import Event, EventKind
from src.domain.memory import rules as memory_rules
from src.domain.memory.models import TOLD, MemoryItem
from src.domain.ports.dictionary import Sense
from src.domain.safety import rules as safety_rules
from src.domain.tools import catalog
from src.domain.tools import rules as tool_rules
from src.infrastructure.ai.llama_client import messages as client_messages
from src.infrastructure.storage.character_catalog import TomlCharacterCatalog
from src.utils import paths

ZONE = UTC
_NOON = time(12, 0)
# The order of the fields that the schema states, which the model follows.
_FIELDS = tuple(conversation_rules.INTERPRETATION_SCHEMA["properties"])  # type: ignore[arg-type]


@dataclass(frozen=True)
class Request:
    """What goes to the model: the messages, the tool schemas, and the JSON
    schema of an interpretation."""

    messages: list[dict]
    tools: list[dict]
    schema: Mapping[str, object] | None


def now_of(example: Example) -> datetime:
    """The time of the example's turn."""
    return datetime.combine(example.today, _NOON, tzinfo=ZONE)


@cache
def templates() -> dict[str, Template]:
    """The ready-made characters, by their ID."""
    catalog_ = TomlCharacterCatalog(paths.resource("characters.toml"))
    return {t.id: t for t in catalog_.templates()}


def system_prompt(character: str) -> str:
    """Layers 1 and 2 with the reasoning rule, as ``core_host`` builds them."""
    description = templates()[character].description
    return (
        f"{conversation_rules.system_text(description)}\n\n"
        f"{conversation_rules.REASONING_RULE}"
    )


def tool_schemas() -> list[dict]:
    """The tool list of a reply, in the OpenAI form that the tool loop sends."""
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": dict(spec.parameters),
            },
        }
        for spec in catalog.SPECS
    ]


def _messages(turns: Sequence[Turn], at: datetime) -> list[Message]:
    return [
        Message(f"m{i}", "c", USER if t.from_user else COMPANION, t.text, at)
        for i, t in enumerate(turns)
    ]


def memory_item(text: str, told: date, number: int = 0) -> MemoryItem:
    """A stored line told at noon on ``told``."""
    return MemoryItem(
        id=f"r{number}",
        kind=TOLD,
        text=text,
        reason=None,
        source_message_id=None,
        importance=None,
        last_retrieved_at=None,
        recorded_at=datetime.combine(told, _NOON, tzinfo=ZONE),
        embedding=None,
    )


def layer_4(example: Example) -> str:
    """The layer 4 of a reply, as ``core_host`` builds it: no mood on a crisis
    turn, and the safety instruction first."""
    remembered = [
        memory_rules.recalled_line(memory_item(r.text, r.told, i), ZONE)
        for i, r in enumerate(example.remembered)
    ]
    instructions = [safety_rules.instruction()] if example.crisis else []
    instructions.append(conversation_rules.show_back_instruction(example.stored))
    mood = ""
    if not example.crisis and example.mood:
        mood = conversation_rules.mood_line(example.mood)
    return conversation_rules.turn_text(mood, remembered, instructions)


def parts(example: Example) -> tuple[str, list[Message], str]:
    """The system text, the history ending with the user's message, and the
    text that joins that message, for a job other than a summary."""
    history = _messages((*example.history, Turn(True, example.message)),
                        now_of(example))
    system = system_prompt(example.character)
    if example.job == "interpretation":
        turn = conversation_rules.interpretation_instruction(
            example.today, example.known
        )
        return system, history, turn
    return system, history, layer_4(example)


def summary_text(example: Example) -> str:
    """The user text of a summary request."""
    return conversation_rules.summary_request(
        example.previous, _messages(example.messages, now_of(example))
    )


def offers_tools(example: Example) -> bool:
    """Every reply offers the tools, except on a crisis turn."""
    return example.job in ("voice", "tools") and not example.crisis


def request(example: Example) -> Request:
    """The request that the application sends for ``example``. Raises
    ``KeyError`` for a character that does not exist."""
    if example.job == "summary":
        return Request(
            [
                {"role": "system", "content": conversation_rules.SUMMARY_SYSTEM},
                {"role": "user", "content": summary_text(example)},
            ],
            [],
            None,
        )
    built = client_messages(*parts(example))
    if example.job == "interpretation":
        return Request(built, [], conversation_rules.INTERPRETATION_SCHEMA)
    return Request(built, tool_schemas() if offers_tools(example) else [], None)


def _assistant(content: str, reasoning: str, **more: object) -> dict:
    message: dict[str, object] = {"role": "assistant", "content": content}
    if reasoning:
        message["reasoning_content"] = reasoning
    message.update(more)
    return message


def answer(example: Example) -> list[dict]:
    """The messages that the model must learn to write for ``example``. A tool
    call is followed by the result that the application would give."""
    if example.job == "interpretation":
        target = example.target if isinstance(example.target, dict) else {}
        ordered = {name: target.get(name) for name in _FIELDS}
        return [_assistant(json.dumps(ordered, ensure_ascii=False), example.reasoning)]
    target = example.target if isinstance(example.target, str) else ""
    if example.job != "tools" or not example.calls:
        return [_assistant(target, example.reasoning)]
    at = now_of(example)
    said: list[dict] = []
    for number, call in enumerate(example.calls):
        call_id = f"call{number}"
        said.append(
            _assistant(
                "",
                example.reasoning if number == 0 else "",
                tool_calls=[
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(dict(call.arguments)),
                        },
                    }
                ],
            )
        )
        said.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": call.name,
                "content": tool_result(
                    call.name,
                    call.arguments,
                    {"character": example.character, **call.data},
                    example.message,
                    at,
                ),
            }
        )
    said.append(_assistant(target, ""))
    return said


# ── tool results ────────────────────────────────────────────────────────────


def tool_result(
    name: str,
    arguments: Mapping[str, object],
    data: Mapping[str, object],
    message: str,
    now: datetime,
) -> str:
    """The sentence that the application gives the model for a tool call. A
    pure tool runs on ``arguments``; a tool that reads stored data reads it from
    ``data``. An unknown tool gives the sentence of a failed tool."""
    match name:
        case "calculate":
            return tool_rules.calculate(str(arguments.get("expression", "")))
        case "date":
            return tool_rules.date_answer(arguments, now)
        case "convert_units":
            return tool_rules.convert(
                arguments.get("value"),
                str(arguments.get("from", "")),
                str(arguments.get("to", "")),
            )
        case "open_in_browser":
            if not tool_rules.asked_to_open(message):
                return tool_rules.NOT_ASKED
            url = tool_rules.browser_url(arguments)
            if url is None:
                return tool_rules.NOT_OPENABLE
            return tool_rules.opened(url, arguments)
        case "define_word":
            return _define(str(arguments.get("word", "")), data)
        case "recall_memory":
            return _recall(str(arguments.get("query", "")), data)
        case "search_conversations":
            return _search(str(arguments.get("query", "")), data, now)
        case "desk_time":
            return _desk_time(data)
        case "app_usage":
            minutes = data.get("minutes")
            if not data.get("awareness", True) or not isinstance(minutes, dict):
                return awareness_rules.app_usage_text(None)
            return awareness_rules.app_usage_text(
                {str(k): int(v) for k, v in minutes.items()}
            )
        case "why_i_feel":
            return _why(data, now)
        case "breathing" | "stretch":
            if data.get("running"):
                return tool_rules.ALREADY_RUNNING
            return tool_rules.started(name)
    return tool_rules.TOOL_FAILED


def _define(word: str, data: Mapping[str, object]) -> str:
    """Senses from ``data``, or else from the dictionary that ships."""
    given = data.get("senses")
    if isinstance(given, list):
        senses = [Sense(str(s["pos"]), str(s["definition"])) for s in given]
        return tool_rules.define_text(word.strip(), senses)
    from src.app.application import DICTIONARY  # the file name it ships under
    from src.infrastructure.storage.dictionary import SqliteDictionary

    dictionary = SqliteDictionary(paths.resource_dir("dictionary", DICTIONARY))
    for form in tool_rules.candidates(word):
        senses = dictionary.senses(form)
        if senses:
            return tool_rules.define_text(form, senses)
    return tool_rules.define_text(word.strip(), [])


def _recall(query: str, data: Mapping[str, object]) -> str:
    found = [
        memory_item(str(item["text"]), date.fromisoformat(str(item["told"])), i)
        for i, item in enumerate(data.get("found") or [])  # type: ignore[union-attr]
    ]
    return memory_rules.recall_text(query, found, ZONE)


def _search(query: str, data: Mapping[str, object], now: datetime) -> str:
    found = [
        Message(
            f"s{i}",
            "c",
            USER if item.get("from", "user") == "user" else COMPANION,
            str(item["text"]),
            now - timedelta(days=int(item.get("days_ago", 1))),
        )
        for i, item in enumerate(data.get("found") or [])  # type: ignore[union-attr]
    ]
    return conversation_rules.found_text(query, found, ZONE)


def _desk_time(data: Mapping[str, object]) -> str:
    if not data.get("awareness", True):
        return awareness_rules.desk_time_text(None)
    since = data.get("since_break_minutes")
    return awareness_rules.desk_time_text(
        DeskTime(
            today_minutes=int(data.get("today_minutes", 0)),  # type: ignore[arg-type]
            since_break_minutes=None if since is None else int(since),  # type: ignore[arg-type]
            at_desk=bool(data.get("at_desk", True)),
        )
    )


def _why(data: Mapping[str, object], now: datetime) -> str:
    """The answer of ``why_i_feel`` for a character that the user chose a day
    ago, after the messages in ``data``."""
    character = str(data.get("character", "yuna"))
    temperaments = {"v1": templates()[character].temperament}
    events = [
        Event(1, now - timedelta(days=1), 0, EventKind.CHARACTER_CHANGED,
              {"version_id": "v1"}, None)
    ]
    if not data.get("moods_on", True):
        events.append(
            Event(2, now - timedelta(hours=12), 0, EventKind.SETTING_CHANGED,
                  {"name": companion_rules.MOODS_ON, "value": False}, None)
        )
    said = sorted(
        data.get("events") or [],  # type: ignore[arg-type]
        key=lambda e: -int(e.get("minutes_ago", 0)),
    )
    for item in said:
        events.append(
            Event(
                len(events) + 1,
                now - timedelta(minutes=int(item.get("minutes_ago", 0))),
                0,
                EventKind.USER_MESSAGE,
                {
                    "class": str(item["class"]),
                    "confidence": float(item.get("confidence", 0.9)),
                    "message_id": f"e{len(events)}",
                },
                None,
            )
        )
    state = companion_rules.fold(companion_rules.initial_state(), events, temperaments)
    recent = [e for e in events if e.occurred_at >= now - timedelta(
        days=companion_rules.CAUSE_DAYS)]
    return companion_rules.explain_feeling(state, recent, temperaments, now, ZONE)
