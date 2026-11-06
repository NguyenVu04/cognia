from datetime import datetime, timezone

import pytest

from src.domain.tools import rules
from src.domain.tools.models import ToolResult

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("expression", "answer"),
    [
        ("12*7", "12*7 = 84"),
        ("0.1+0.2", "0.1+0.2 = 0.3"),
        ("(1+2)*3^2", "(1+2)*3^2 = 27"),
        ("-3^2", "-3^2 = -9"),
        ("2^-1", "2^-1 = 0.5"),
        ("10/3", "10/3 = 3.33333333333333"),
        ("7 % 3", "7 % 3 = 1"),
        ("12 × 7", "12 × 7 = 84"),
    ],
)
def test_calculate(expression: str, answer: str) -> None:
    assert rules.calculate(expression) == answer


@pytest.mark.parametrize(
    ("expression", "sentence"),
    [
        ("1/0", rules.DIVIDES_BY_ZERO),
        ("0^-1", rules.DIVIDES_BY_ZERO),
        ("2^1000", rules.TOO_LARGE),
        ("__import__('os')", rules.NOT_ARITHMETIC),
        ("", rules.NOT_ARITHMETIC),
        ("3-", rules.NOT_ARITHMETIC),
        ("((1)", rules.NOT_ARITHMETIC),
        ("1+" * 150, rules.NOT_ARITHMETIC),
    ],
)
def test_calculate_refuses(expression: str, sentence: str) -> None:
    assert rules.calculate(expression) == sentence


@pytest.mark.parametrize(
    ("arguments", "answer"),
    [
        ({"op": "today"}, "Today is Friday 6 November 2026."),
        ({"op": "weekday", "date": "2026-12-25"}, "25 December 2026 is a Friday."),
        (
            {"op": "between", "date": "2026-11-06", "other": "2026-12-25"},
            "From 6 November 2026 to 25 December 2026 is 49 days.",
        ),
        (
            {"op": "between", "date": "2026-12-25", "other": "2026-11-06"},
            "From 6 November 2026 to 25 December 2026 is 49 days.",
        ),
        (
            {"op": "add_days", "days": 10},
            "10 days after 6 November 2026 is Monday 16 November 2026.",
        ),
        (
            {"op": "add_days", "date": "2026-11-06", "days": -1},
            "1 day before 6 November 2026 is Thursday 5 November 2026.",
        ),
    ],
)
def test_date(arguments: dict, answer: str) -> None:
    assert rules.date_answer(arguments, NOW) == answer


def test_date_bad_input() -> None:
    assert rules.date_answer({"op": "weekday", "date": "25/12"}, NOW) == (
        "I can't read the date '25/12'. Dates are YYYY-MM-DD."
    )


def test_date_unknown_op() -> None:
    assert rules.date_answer({"op": "moon"}, NOW) == rules.TOOL_FAILED


@pytest.mark.parametrize(
    ("value", "source", "target", "answer"),
    [
        (5, "km", "mi", "5 km is 3.11 mi."),
        (100, "C", "F", "100 C is 212 F."),
        (0, "°C", "K", "0 °C is 273.15 K."),
        (1, "lb", "kg", "1 lb is 0.45 kg."),
    ],
)
def test_convert(value, source: str, target: str, answer: str) -> None:
    assert rules.convert(value, source, target) == answer


@pytest.mark.parametrize(
    ("value", "source", "target"), [(1, "km", "kg"), ("five", "km", "mi")]
)
def test_convert_refuses(value, source: str, target: str) -> None:
    refusal = f"I can't convert {source} to {target}."
    assert rules.convert(value, source, target) == refusal


@pytest.mark.parametrize(
    ("text", "asked"),
    [
        ("open the bbc site", True),
        ("Can you show me a map of Hanoi?", True),
        ("look it up for me", True),
        ("what's the news?", False),
        ("I opened a shop", False),
    ],
)
def test_asked_to_open(text: str, asked: bool) -> None:
    assert rules.asked_to_open(text) is asked


@pytest.mark.parametrize(
    ("arguments", "url"),
    [
        ({"url": "https://bbc.co.uk"}, "https://bbc.co.uk"),
        ({"url": "javascript:alert(1)"}, None),
        ({"url": "file:///C:/secret.txt"}, None),
        ({"search": "cat food"}, "https://duckduckgo.com/?q=cat+food"),
        ({}, None),
    ],
)
def test_browser_url(arguments: dict, url: str | None) -> None:
    assert rules.browser_url(arguments) == url


def test_opened_sentences() -> None:
    search = {"search": "cats"}
    assert rules.opened(rules.browser_url(search), search) == (
        "Opened a search for 'cats' in the user's browser."
    )
    assert rules.opened("https://x.org", {"url": "https://x.org"}) == (
        "Opened https://x.org in the user's browser."
    )


def test_numbers_are_canonical() -> None:
    assert rules.numbers("1,200 or 3.50 at 10:30, then 95.") == (
        "1200", "3.5", "10", "30", "95",
    )


def test_unchecked_numbers() -> None:
    assert rules.unchecked_numbers("87 or 95, 95", ["87 minutes"]) == ("95",)
    assert rules.unchecked_numbers("It is 84.", ["12*7 = 84"]) == ()


def test_number_note() -> None:
    results = [ToolResult("calculate", "12*7 = 84")]

    assert rules.number_note(("85",), results) == (
        "Not from what I checked: 85 · I found: 12*7 = 84"
    )
    assert rules.number_note((), results) == ""



@pytest.mark.parametrize(("name", "seconds"), [("breathing", 70), ("stretch", 80)])
def test_activity_lengths(name: str, seconds: int) -> None:
    assert sum(step.seconds for step in rules.activity(name)) == seconds


def test_breathing_steps_in_order() -> None:
    labels = [step.label for step in rules.activity("breathing")[:3]]

    assert labels == ["breathe in", "hold", "breathe out"]


def test_activity_unknown() -> None:
    with pytest.raises(ValueError):
        rules.activity("yoga")


def test_started_sentences() -> None:
    assert rules.started("breathing") == "Started: breathing together for 70 seconds."
    assert rules.started("stretch") == "Started: stretching together for 80 seconds."



@pytest.mark.parametrize(
    ("word", "forms"),
    [
        ("Studies", ("studies", "study", "studi", "studie")),
        ("baked", ("baked", "bak", "bake")),
        ("running", ("running", "runn", "runne")),
        ("cat", ("cat",)),
    ],
)
def test_candidates(word: str, forms: tuple[str, ...]) -> None:
    assert rules.candidates(word) == forms


def test_define_text() -> None:
    from src.domain.ports import Sense

    senses = [Sense("noun", "sloping land"), Sense("verb", "tip laterally")]

    assert rules.define_text("bank", senses) == (
        "bank (noun): sloping land; bank (verb): tip laterally"
    )
    assert rules.define_text("zyxq", []) == (
        "The dictionary on this machine has no entry for 'zyxq'."
    )
