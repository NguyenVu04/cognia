"""Small examples for the tests to change with ``dataclasses.replace``."""

from dataclasses import replace
from datetime import date

from finetuning.examples import Example, ToolUse, Turn

DAY = date(2026, 11, 7)


def voice(**changes) -> Example:
    example = Example(
        id="voice-1",
        job="voice",
        today=DAY,
        character="rin",
        history=(Turn(True, "Hey."), Turn(False, "Hmph. You're back.")),
        message="I passed my driving test!",
        mood="pleased",
        reasoning="Good news. Tease, then be glad.",
        target="Ehh? You actually passed? ...Not bad. Not bad at all.",
        tags=("good_news",),
    )
    return replace(example, **changes)


def interpretation(**changes) -> Example:
    example = Example(
        id="interp-1",
        job="interpretation",
        today=DAY,
        character="yuna",
        message="I'm writing my thesis on emotion models.",
        reasoning="A lasting fact about their work.",
        target={
            "facts": ["Is writing a thesis on emotion models"],
            "importance": 7,
            "crisis": False,
            "event_class": "nothing",
            "confidence": 0.8,
            "style_request": None,
        },
    )
    return replace(example, **changes)


def summary(**changes) -> Example:
    example = Example(
        id="sum-1",
        job="summary",
        today=DAY,
        messages=(Turn(True, "I walked by the river."), Turn(False, "Sounds nice.")),
        target="The user walked by the river. The companion said it sounded nice.",
    )
    return replace(example, **changes)


def tools(**changes) -> Example:
    example = Example(
        id="tools-1",
        job="tools",
        today=DAY,
        character="mira",
        message="What's 12*7?",
        mood="lively",
        calls=(ToolUse("calculate", {"expression": "12*7"}),),
        reasoning="A sum. Use calculate.",
        target="It's 84! Ooh, that was a quick one.",
    )
    return replace(example, **changes)
