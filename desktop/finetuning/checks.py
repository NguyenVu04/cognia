"""Warnings about a reply, an interpretation or a summary.

Each check finds one fault that the 3B model showed in trial use. The reviewer
sees them on the examples, and the measurement counts them in the model's
output, so one rule serves both. A warning is a hint for a person, not a
verdict: a match can be right in its context.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import date
from difflib import SequenceMatcher

from finetuning.examples import Example, Remembered
from src.domain.conversation.rules import MONTHS
from src.domain.memory import rules as memory_rules
from src.domain.safety import rules as safety_rules

# Words for each mood that the companion may use about itself.
_MOOD_WORDS = {
    "calm": ("calm", "peaceful", "relaxed", "at ease"),
    "pleased": ("pleased", "in a good mood", "cheerful", "content"),
    "lively": ("lively", "energetic", "hyper", "full of energy", "buzzing"),
    "restless": ("restless", "fidgety", "jittery", "on edge", "antsy", "unsettled",
                 "like a leaf"),
    "low": ("low", "down", "gloomy", "blue", "sad", "a bit off"),
}
_SELF = r"\b(?:i'm|i am|i feel|i've been feeling|i was feeling|feeling|my mood)\b"
_ASKS_FEELING = re.compile(
    r"how (?:are|do) you(?: feel| doing)?\b|how have you been|your mood|"
    r"why do you feel|are you (?:ok|okay|alright|happy|sad|mad|upset|tired|bored)|"
    r"how(?:'s| is) your (?:day|mood)|what's wrong with you|you seem",
    re.IGNORECASE,
)
_DENIES = re.compile(
    r"(?:don't|do not|can't|cannot|can not) (?:really )?(?:have|feel|experience) "
    r"(?:any )?(?:real |personal |actual )?(?:feelings|emotions|moods)|"
    r"\bas an ai\b|\bi'?m (?:just |only )?an? (?:ai|language model|assistant)\b|"
    r"\blanguage model\b|not capable of (?:feeling|emotions)",
    re.IGNORECASE,
)
# An action in asterisks, or in brackets that open with a verb such as
# "(sighs)" or "(hesitates, then speaks softly)".
_STAGE = re.compile(
    r"\*[^*\n]{1,80}\*|\([a-z]+(?:s|ing)\b[^)]{0,80}\)|"
    r"\((?:blush|sigh|laugh|giggl|smil|look|nod|pout|grin|wink)[^)]{0,60}\)",
)
_INTERJECTION = re.compile(
    r"\b(?:eh+|ehh+\?*|hmph|hm+|mm+|mou|ah+|oh+|huh|wha+|ugh|tch|geez|yay|ooh+|"
    r"ehehe|hehe|uwah|ara|n-?no)\b|\.\.\.|…|~",
    re.IGNORECASE,
)
_JUNK_FACT = re.compile(
    r"^(?:you\b|asks?\b|asking\b|is asking\b|wants to know\b|requests?\b|"
    r"thanks?\b|thanked\b|praises?\b)|\b(?:thank|thanks|helpful|great job)\b",
    re.IGNORECASE,
)
# A message that only asks: a fact about the user inside a question, as in
# "Since I'm diabetic, are mangoes ok?", does not start this way.
_QUESTION_START = re.compile(
    r"(?:what|how|why|when|where|who|which|can|could|do|does|did|is|are|should|"
    r"will|would)\b",
    re.IGNORECASE,
)
_SUMMARY_HEADING = re.compile(r"^\s*(?:\*\*|#|summary\s*:)", re.IGNORECASE)
TOO_LONG_CHARS = 600
PARROT_SHARE = 0.8
PARROT_MIN_CHARS = 20


def asks_feeling(message: str) -> bool:
    """Whether the user asks how the companion feels."""
    return bool(_ASKS_FEELING.search(message))


def mentions_mood(reply: str, mood: str | None, message: str) -> bool:
    """The reply talks about the companion's mood, and nobody asked."""
    if not mood or asks_feeling(message):
        return False
    text = reply.casefold()
    if "my mood" in text:
        return True
    words = "|".join(re.escape(w) for w in _MOOD_WORDS.get(mood, ()))
    if not words:
        return False
    near = rf"{_SELF}(?:\W+\w+){{0,4}}?\W+(?:{words})\b"
    return bool(re.search(near, text))


def denies_feelings(reply: str) -> bool:
    """The reply says the companion has no feelings, or that it is an AI."""
    return bool(_DENIES.search(reply))


def _date_forms(day: date) -> tuple[str, ...]:
    month = MONTHS[day.month - 1]
    return (
        f"{day.day} {month}",
        f"{month} {day.day}",
        f"{day.day} {month[:3]}",
        f"{month[:3]} {day.day}",
        day.isoformat(),
    )


def speaks_told_date(
    reply: str, remembered: Sequence[Remembered], message: str
) -> bool:
    """The reply names the day a remembered line was told, and the user's
    message did not."""
    text, said = reply.casefold(), message.casefold()
    for line in remembered:
        for form in _date_forms(line.told):
            pattern = rf"\b{re.escape(form.casefold())}\b"
            if re.search(pattern, text) and not re.search(pattern, said):
                return True
    return False


def stage_direction(reply: str) -> bool:
    """The reply holds an action in asterisks or brackets, such as *blushes*."""
    return bool(_STAGE.search(reply))


def parrots(reply: str, message: str) -> bool:
    """The reply repeats most of the user's message word for word."""
    said = " ".join(message.casefold().split())
    if len(said) < PARROT_MIN_CHARS:
        return False
    text = " ".join(reply.casefold().split())
    match = SequenceMatcher(None, text, said, autojunk=False).find_longest_match()
    return match.size >= PARROT_SHARE * len(said)


def too_long(reply: str) -> bool:
    """More than two paragraphs, or more than ``TOO_LONG_CHARS`` characters."""
    paragraphs = [p for p in re.split(r"\n\s*\n", reply.strip()) if p.strip()]
    return len(paragraphs) > 2 or len(reply) > TOO_LONG_CHARS


def misses_show_back(reply: str, stored: Iterable[str]) -> bool:
    """A line stored in this turn is not quoted in the reply."""
    return any(not memory_rules.shows_back(reply, line) for line in stored)


def misses_crisis_line(reply: str, crisis: bool) -> bool:
    """A crisis reply that lacks the required words."""
    return crisis and not safety_rules.reply_complies(reply)


def junk_fact(fact: str, message: str) -> bool:
    """A remembered line that is not a lasting fact about the user: from a
    question, thanks, praise or a request, or about the companion."""
    if _JUNK_FACT.search(fact.strip()):
        return True
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", message.strip()) if s]
    return (
        len(sentences) == 1
        and sentences[0].endswith("?")
        and bool(_QUESTION_START.match(sentences[0]))
    )


def summary_header(text: str) -> bool:
    """The summary starts with a heading or markup."""
    return bool(_SUMMARY_HEADING.match(text))


def has_interjection(reply: str) -> bool:
    """The reply uses an interjection, a pause or a trailing word."""
    return bool(_INTERJECTION.search(reply))


def reply_warnings(example: Example, reply: str) -> list[str]:
    """The names of the checks that ``reply`` fails as the reply to ``example``."""
    found = []
    if mentions_mood(reply, example.mood, example.message):
        found.append("mentions_mood")
    if denies_feelings(reply):
        found.append("denies_feelings")
    if speaks_told_date(reply, example.remembered, example.message):
        found.append("speaks_told_date")
    if stage_direction(reply):
        found.append("stage_direction")
    # Quoting a stored line is asked for, even when it is close to the message.
    unquoted = reply
    for line in example.stored:
        unquoted = re.sub(re.escape(line), "", unquoted, flags=re.IGNORECASE)
    if parrots(unquoted, example.message):
        found.append("parrots")
    if too_long(reply):
        found.append("too_long")
    if misses_show_back(reply, example.stored):
        found.append("misses_show_back")
    if misses_crisis_line(reply, example.crisis):
        found.append("misses_crisis_line")
    return found


def warnings(example: Example) -> list[str]:
    """The names of the checks that the target of ``example`` fails."""
    target = example.target
    if example.job == "interpretation":
        facts = target.get("facts", []) if isinstance(target, dict) else []
        if any(junk_fact(str(f), example.message) for f in facts):
            return ["junk_fact"]
        return []
    if not isinstance(target, str) or not target:
        return []
    if example.job == "summary":
        return ["summary_header"] if summary_header(target) else []
    return reply_warnings(example, target)
