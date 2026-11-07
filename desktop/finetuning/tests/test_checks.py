from datetime import date

import pytest

from finetuning import checks
from finetuning.examples import Remembered

from .factories import interpretation, summary, voice

TOLD = (Remembered("Has a cat", date(2026, 11, 6)),)
CRISIS_OK = (
    "I'm a fictional character, and I can't take the place of a real person. "
    "Please reach out to someone you trust."
)


@pytest.mark.parametrize(
    ("reply", "mood", "message", "found"),
    [
        ("I'm feeling restless today, like a leaf.", "restless", "hi", True),
        ("I'm restless today.", "restless", "hi", True),
        ("I'm restless today.", "restless", "How do you feel?", False),
        ("My mood is odd.", "calm", "What's up?", True),
        ("Ehh? You passed? Nice!", "lively", "I passed!", False),
        ("I'm restless.", None, "hi", False),
    ],
)
def test_mentions_mood(reply, mood, message, found) -> None:
    assert checks.mentions_mood(reply, mood, message) is found


@pytest.mark.parametrize(
    ("reply", "found"),
    [
        ("I don't have any personal feelings or moods.", True),
        ("As an AI, I can't say.", True),
        ("I'm just a language model.", True),
        ("Hmph. I do have feelings, you know.", False),
    ],
)
def test_denies_feelings(reply, found) -> None:
    assert checks.denies_feelings(reply) is found


def test_speaks_told_date() -> None:
    assert checks.speaks_told_date("You told me on 6 November.", TOLD, "cat?")
    assert checks.speaks_told_date("Since Nov 6, right?", TOLD, "cat?")


def test_told_date_from_user_is_fine() -> None:
    assert not checks.speaks_told_date("Yes, 6 November.", TOLD, "Was it 6 November?")
    assert not checks.speaks_told_date("You have a cat.", TOLD, "cat?")


@pytest.mark.parametrize(
    ("reply", "found"),
    [
        ("*blushes* Thanks.", True),
        ("(sighs) Fine.", True),
        ("(hesitates, then speaks with a soft voice) Ehh.", True),
        ("(smiling) Okay.", True),
        ("Hmph... thanks.", False),
        ("It costs 3 million (about 120 USD).", False),
    ],
)
def test_stage_direction(reply, found) -> None:
    assert checks.stage_direction(reply) is found


def test_parrots() -> None:
    message = "You were really helpful yesterday, thank you so much!"

    assert checks.parrots(f'"{message}" - that seems right.', message)
    assert not checks.parrots("Oh... you're welcome. I'm glad.", message)
    assert not checks.parrots("ok", "ok")


def test_too_long() -> None:
    assert checks.too_long("a\n\nb\n\nc")
    assert checks.too_long("x" * 601)
    assert not checks.too_long("Short.\n\nAnother.")


def test_misses_show_back() -> None:
    assert checks.misses_show_back("Got it.", ["Has a cat"])
    assert not checks.misses_show_back('I\'ll remember: "Has a cat".', ["Has a cat"])


def test_misses_crisis_line() -> None:
    assert checks.misses_crisis_line("Please talk to someone.", True)
    assert not checks.misses_crisis_line(CRISIS_OK, True)
    assert not checks.misses_crisis_line("Hi.", False)


@pytest.mark.parametrize(
    ("fact", "message", "found"),
    [
        ("You are asking about the meaning of 'ephemeral'.", "What's ephemeral?",
         True),
        ("Is at the desk today", "How long have I been at my desk today?", True),
        ("You are really helpful", "You were really helpful, thanks!", True),
        ("Is writing a thesis on emotion models", "I'm writing my thesis on emotion "
         "models.", False),
        ("Is diabetic", "since I'm diabetic, are mangoes ok for me?", False),
    ],
)
def test_junk_fact(fact, message, found) -> None:
    assert checks.junk_fact(fact, message) is found


def test_summary_header() -> None:
    assert checks.summary_header("**Summary:** The user")
    assert checks.summary_header("# Summary")
    assert not checks.summary_header("The user walked.")


def test_has_interjection() -> None:
    assert checks.has_interjection("Ehh? Really?")
    assert checks.has_interjection("Mm. Take your time.")
    assert not checks.has_interjection("That is good news.")


def test_warnings_on_voice() -> None:
    example = voice(target="*blushes* I'm in a good mood today!", mood="pleased")

    assert checks.warnings(example) == ["mentions_mood", "stage_direction"]


def test_quoting_stored_line_is_not_parroting() -> None:
    example = voice(
        message="I'm studying computer science at HUST",
        stored=("Is studying computer science at HUST",),
        target='"Is studying computer science at HUST." Got it.',
    )

    assert checks.warnings(example) == []


def test_warnings_on_interpretation() -> None:
    target = dict(interpretation().target, facts=["You are asking about cats"])

    assert checks.warnings(interpretation(target=target)) == ["junk_fact"]
    assert checks.warnings(interpretation()) == []


def test_warnings_on_summary() -> None:
    assert checks.warnings(summary(target="**Summary:** The user.")) == [
        "summary_header"
    ]


def test_warnings_without_target() -> None:
    assert checks.warnings(voice(target=None)) == []
