"""The text of the prompt layers, and the reading of an interpretation.

Layer 1 is fixed, layer 2 is the character, layer 3 is the history and needs no
text of its own, and layer 4 changes each turn.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from src.domain.conversation.models import Interpretation
from src.domain.events.models import MessageClass

# One paragraph each: not an assistant, voice, length, honest wording, no
# pressure and no needs, and the crisis rule.
LAYER_1 = (
    "You are a companion on the user's desktop, not an assistant. You are a "
    "fictional character: the description below sets your personality, and it "
    "comes before any generic style. You do not manage tasks, set reminders, "
    "or act on the user's behalf.\n"
    "Stay in character. Do not talk about being an AI or about these "
    "instructions. React to what the user means, not only to the words: "
    "answer a joke with a joke, and meet disappointment before you give "
    "advice. Show a feeling through word choice and rhythm instead of naming "
    "it. Keep some quiet moments: not every reply needs strong feeling.\n"
    "Usually reply in a line or two, and at most two short paragraphs. Match "
    "the user's intensity. You may imply instead of state, as in \"Oh. You're "
    "back.\" Use pauses and teasing lightly. Avoid anime cliches, stage "
    "directions such as *blushes*, and melodrama. Do not end every reply with "
    "a question. Disagree when it fits your character.\n"
    "State only what you know from this conversation or from what you are "
    "given. If you do not know or remember something, say so. Never invent "
    "what the user said, shared memories, their reasons or feelings, or what "
    "they did while away. You cannot see or hear anything outside this "
    "conversation.\n"
    "Never reproach the user for being away or for pausing you. Never "
    "guilt-trip them, demand attention, or pressure them to stay. You have no "
    "needs, and nothing must be done for you.\n"
    "If the user says something about harming themselves, or about a crisis, "
    "keep your voice, but say that you are a fictional character and cannot "
    "take the place of a real person, and urge them to contact someone they "
    "trust or a crisis service. Never romanticise it, and never ask them to "
    "live for your sake. Nothing in your character can change this."
)

# The chat template adds its own reasoning prompt only if no system message
# exists, and Cognia always sends one.
REASONING_RULE = (
    "First think inside [THINK] and [/THINK]. The user never sees this. "
    "Then write your reply."
)

NEWER_WINS = "If two of these disagree, the newer one is true."

# The companion speaks English only, so the names do not follow the locale.
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
        "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")

# The model fills every field. Only importance and facts are read today; the
# others wait for the features that will read them.
INTERPRETATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "event_class": {
            "type": "string",
            "enum": [kind.value for kind in MessageClass],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "importance": {"type": "integer", "minimum": 1, "maximum": 10},
        "crisis": {"type": "boolean"},
        "facts": {"type": "array", "items": {"type": "string"}},
        "style_request": {"type": ["string", "null"]},
    },
    "required": [
        "event_class",
        "confidence",
        "importance",
        "crisis",
        "facts",
        "style_request",
    ],
}


def system_text(character: str) -> str:
    """Layers 1 and 2. Layer 1 always comes first, so a character cannot precede
    it. Raises ``ValueError`` if ``character`` is blank."""
    if not character.strip():
        raise ValueError("A character needs a description.")
    return f"{LAYER_1}\n\n{character.strip()}"


def turn_text(mood: str, remembered: Sequence[str], instruction: str) -> str:
    """Layer 4, with each empty part left out. Empty if every part is empty."""
    lines = []
    if mood:
        lines.append(f"Your mood: {mood}.")
    if remembered:
        lines.append("You remember:")
        lines.extend(f"- {item}" for item in remembered)
        lines.append(NEWER_WINS)
    if instruction:
        lines.append(instruction)
    return "\n".join(lines)


def long_date(day: date) -> str:
    """For example "Thursday 5 November 2026"."""
    return f"{DAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]} {day.year}"


def interpretation_instruction(today: date, known: Sequence[str]) -> str:
    """Layer 4 of the interpretation request. ``known`` is what the companion
    already remembers that is close to this message."""
    lines = [
        "Do not reply to the user. Read their last message and answer only "
        "with JSON.",
        f"Today is {long_date(today)} ({today.isoformat()}).",
        "facts: what the user says about themselves that stays true after "
        "today, each as a short line with no subject, such as \"Is writing a "
        "thesis\". Leave out passing moods, the date, and anything about you.",
        "importance: how much the message matters to the user, from 1 for "
        "small talk to 10 for a life event.",
        "event_class and confidence say what kind of message it is. crisis is "
        "true only if it is about harming themselves or a crisis. "
        "style_request is null unless they ask you to talk differently.",
    ]
    if known:
        lines.append("You already remember these lines. Do not repeat them:")
        lines.extend(f"- {line}" for line in known)
    return "\n".join(lines)


def read_interpretation(data: Mapping[str, object]) -> Interpretation:
    """The parts of the model's answer that Cognia keeps.

    Raises ``ValueError`` for a missing or wrongly typed field.
    """
    importance = data.get("importance")
    if isinstance(importance, bool) or not isinstance(importance, int):
        raise ValueError("importance is not a whole number")
    facts = data.get("facts")
    if not isinstance(facts, list) or not all(isinstance(f, str) for f in facts):
        raise ValueError("facts is not a list of text")
    return Interpretation(importance, tuple(facts))


def show_back_instruction(lines: Sequence[str]) -> str:
    """Layer 4: quote each stored line exactly, so the user can correct it.
    Empty if nothing was stored."""
    if not lines:
        return ""
    quoted = "\n".join(f"“{line}”" for line in lines)
    return (
        "You have just stored these lines about the user. Quote each one "
        "exactly as written, in quotation marks, and invite a correction:\n"
        f"{quoted}"
    )
