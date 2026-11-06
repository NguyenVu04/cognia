"""The tools the model can call. The set is closed: a new tool is a change here.

Each tool has a description for the model, a label the chat shows while it
runs, and the JSON Schema of its arguments.
"""

from __future__ import annotations

from src.domain.tools.models import ToolSpec

# After this many rounds of tool calls, the model must answer.
TOOL_ROUNDS = 3

_NONE: dict[str, object] = {"type": "object", "properties": {}, "required": []}


def _one(name: str, kind: str = "string") -> dict[str, object]:
    return {"type": "object", "properties": {name: {"type": kind}}, "required": [name]}


SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "calculate",
        "Work out an arithmetic expression exactly, with + - * / % ^ and brackets. "
        "Use it for every sum.",
        _one("expression"),
        "working it out",
        data=True,
    ),
    ToolSpec(
        "date",
        "Dates counted from today. op \"today\": today's date. op \"weekday\": the "
        "weekday of `date`. op \"between\": the days from `date` to `other`. op "
        "\"add_days\": the date `days` after `date` (a negative number goes back). "
        "Dates are YYYY-MM-DD; `date` is today if left out.",
        {
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "enum": ["today", "weekday", "between", "add_days"],
                },
                "date": {"type": "string"},
                "other": {"type": "string"},
                "days": {"type": "integer"},
            },
            "required": ["op"],
        },
        "checking the date",
        data=True,
    ),
    ToolSpec(
        "convert_units",
        "Convert a length, a weight or a temperature. Units: mm, cm, m, km, in, "
        "ft, yd, mi, g, kg, oz, lb, C, F, K.",
        {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "from": {"type": "string"},
                "to": {"type": "string"},
            },
            "required": ["value", "from", "to"],
        },
        "converting",
        data=True,
    ),
    ToolSpec(
        "open_in_browser",
        "Open a web page (`url`) or a web search (`search`) in the user's own "
        "browser. Use it only when the user asks you to open, show or look "
        "something up. You cannot read the page.",
        {
            "type": "object",
            "properties": {"url": {"type": "string"}, "search": {"type": "string"}},
            "required": [],
        },
        "opening your browser",
        data=False,
    ),
    ToolSpec(
        "why_i_feel",
        "Your feeling now and the recorded events that moved it, with their "
        "figures. Use it when the user asks how or why you feel.",
        _NONE,
        "looking at my feelings",
        data=True,
    ),
    ToolSpec(
        "recall_memory",
        "Search the lines you have stored about the user, by meaning. Each comes "
        "with the day it was told. It never changes them.",
        _one("query"),
        "remembering",
        data=True,
    ),
    ToolSpec(
        "search_conversations",
        "Find earlier messages in your past conversations with the user that hold "
        "all the given words.",
        _one("query"),
        "looking through our conversations",
        data=True,
    ),
    ToolSpec(
        "desk_time",
        "The minutes the user has been at the machine today, and since their last "
        "break of 5 minutes or more. Say \"at the machine\", never \"working\".",
        _NONE,
        "checking your time at the machine",
        data=True,
    ),
    ToolSpec(
        "app_usage",
        "The minutes in each application today, by application name only.",
        _NONE,
        "checking your applications",
        data=True,
    ),
    ToolSpec(
        "define_word",
        "The meaning of an English word, from the dictionary on this machine.",
        _one("word"),
        "looking it up",
        data=False,
    ),
    ToolSpec(
        "breathing",
        "Start a breathing exercise together: 70 seconds, in 4, hold 4, out 6. Use "
        "it when the user wants to calm down, or agrees to breathe together.",
        _NONE,
        "getting ready to breathe",
        data=False,
    ),
    ToolSpec(
        "stretch",
        "Start a short stretch together: four stretches of 20 seconds. Use it when "
        "the user wants to stretch, or agrees to.",
        _NONE,
        "getting ready to stretch",
        data=False,
    ),
)

#: The tools whose data lives on the core thread.
CORE_TOOLS = frozenset(
    {"why_i_feel", "search_conversations", "desk_time", "app_usage", "breathing",
     "stretch"}
)


def spec(name: str) -> ToolSpec | None:
    """The tool called ``name``, or ``None`` if there is none."""
    return next((s for s in SPECS if s.name == name), None)
