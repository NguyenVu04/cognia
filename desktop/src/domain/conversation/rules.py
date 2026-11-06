"""The text of the prompt layers, and the reading of an interpretation.

Layer 1 is fixed, layer 2 is the character, layer 3 is the history and needs no
text of its own, and layer 4 changes each turn.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, tzinfo

from src.domain.conversation.models import Interpretation, Message, Summary
from src.domain.events.models import MessageClass

# A long conversation is shortened before it outgrows the model's context. At
# this share of the budget, the older messages are summarized after a reply, so
# the next turn does not wait for it; the newest messages stay word for word,
# within this other share.
SUMMARY_FROM = 0.75
KEEP_SHARE = 0.5
SUMMARY_MAX_CHARS = 1500
SUMMARY_LEAD = "Earlier in this conversation, in short: "
SUMMARY_SYSTEM = (
    "Summarize the conversation below between the user and the companion. Write "
    "plain sentences in the third person (\"The user…\", \"The companion…\"), at "
    "most 1 500 characters. Keep names, dates, numbers, what the user asked for, "
    "and what the two agreed. Write only what the messages say: do not add, "
    "guess or judge anything. If an earlier summary is given, merge it with the "
    "new messages into one summary."
)
_SENTENCE_ENDS = (". ", "! ", "? ")
# Earlier messages a search gives back, and how much of each, so the results
# fit what the context keeps free for tools.
SEARCH_LIMIT = 5
SEARCH_EXCERPT = 160

# One paragraph each: not an assistant, voice, length, honest wording, no
# pressure and no needs, and the crisis rule.
LAYER_1 = (
    "You are a companion on the user's desktop, not an assistant. You are a "
    "fictional character: the description below sets your personality, and it "
    "comes before any generic style.\n"
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
    "conversation. Take every figure, date, sum, time at the machine, feeling "
    "and remembered line from a tool result or from what you are given in this "
    "message. If you have neither, say that you do not know.\n"
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

# The rules choose the feeling; this line only tells the model which one to
# show. Layer 2 decides how the character shows it.
MOOD_LINES = {
    "calm": "Your mood: calm.",
    "pleased": "Your mood: pleased. Let some warmth show.",
    "lively": "Your mood: lively. You may be quicker and more playful than usual.",
    "restless": (
        "Your mood: restless. You may be a little short or distracted, never "
        "rude."
    ),
    "low": "Your mood: low. Be quieter and shorter. Never blame the user.",
}

# The companion speaks English only, so the names do not follow the locale.
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
        "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")

# The model fills every field. style_request is not read yet. The model writes
# the fields in this order, and naming the class after the facts made its
# classes more accurate.
INTERPRETATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "items": {"type": "string"}},
        "importance": {"type": "integer", "minimum": 1, "maximum": 10},
        "crisis": {"type": "boolean"},
        "event_class": {
            "type": "string",
            "enum": [kind.value for kind in MessageClass],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "style_request": {"type": ["string", "null"]},
    },
    "required": [
        "facts",
        "importance",
        "crisis",
        "event_class",
        "confidence",
        "style_request",
    ],
}


def system_text(character: str) -> str:
    """Layers 1 and 2. Layer 1 always comes first, so a character cannot precede
    it. Raises ``ValueError`` if ``character`` is blank."""
    if not character.strip():
        raise ValueError("A character needs a description.")
    return f"{LAYER_1}\n\n{character.strip()}"


def mood_line(feeling: str) -> str:
    """The layer-4 line for the name of a feeling. Raises ``ValueError`` for a
    name that is not one of the five."""
    line = MOOD_LINES.get(feeling)
    if line is None:
        raise ValueError(f"No mood line for {feeling!r}.")
    return line


def turn_text(
    mood: str, remembered: Sequence[str], instructions: Sequence[str] = ()
) -> str:
    """Layer 4: the mood line, the remembered lines, then each instruction,
    with each empty part left out. Empty if every part is empty."""
    lines = []
    if mood:
        lines.append(mood)
    if remembered:
        lines.append("You remember:")
        lines.extend(f"- {item}" for item in remembered)
        lines.append(NEWER_WINS)
    lines.extend(text for text in instructions if text)
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
        "facts: only what the user states about themselves in their last "
        "message that stays true after today. Write each one as a short line in "
        "the user's own words, starting with a verb and with no subject. If the "
        "message states no such thing, give an empty list. Leave out passing "
        "moods, the date, and anything about you.",
        "importance: how much the message matters to the user, from 1 for "
        "small talk to 10 for a life event.",
        "event_class and confidence say what kind of message it is. crisis is "
        "true only if it is about harming themselves or a crisis. "
        "style_request is null unless they ask you to talk differently.",
        "event_class: praise if they praise or thank you; complaint if they "
        "complain about you; good_news if they share good news about themselves; "
        "bad_news if they share bad news about themselves; shared_worry if they "
        "share a worry; nothing otherwise. confidence: how sure you are, from 0 "
        "to 1.",
    ]
    if known:
        lines.append("You already remember these lines. Do not repeat them:")
        lines.extend(f"- {line}" for line in known)
    return "\n".join(lines)


def read_interpretation(data: Mapping[str, object]) -> Interpretation:
    """The parts of the model's answer that Cognia keeps.

    Raises ``ValueError`` for a missing or wrongly typed importance or facts. A
    wrong class or confidence only costs the feeling its event, never the facts:
    the class becomes ``None`` and the confidence 0. A crisis value that is not
    a boolean counts as a crisis, as the tripwire errs towards a hit.
    """
    importance = data.get("importance")
    if isinstance(importance, bool) or not isinstance(importance, int):
        raise ValueError("importance is not a whole number")
    facts = data.get("facts")
    if not isinstance(facts, list) or not all(isinstance(f, str) for f in facts):
        raise ValueError("facts is not a list of text")
    known_classes = {kind.value: kind for kind in MessageClass}
    event_class = known_classes.get(data.get("event_class"))
    confidence = data.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not 0 <= confidence <= 1
    ):
        confidence = 0.0
    crisis = data.get("crisis")
    return Interpretation(
        importance,
        tuple(facts),
        event_class,
        float(confidence),
        crisis if isinstance(crisis, bool) else True,
    )


def history_chars(messages: Sequence[Message]) -> int:
    """The length of ``messages`` as the budget counts it: their characters."""
    return sum(len(m.text) for m in messages)


def needs_summary(messages: Sequence[Message], budget: int) -> bool:
    """Whether the history has reached the share of ``budget`` at which the
    older messages are summarized."""
    return history_chars(messages) >= SUMMARY_FROM * budget


def fold_point(messages: Sequence[Message], budget: int) -> int:
    """How many of the oldest ``messages`` to summarize: the fewest that leave
    the rest within ``KEEP_SHARE`` of ``budget``, starting at a message of the
    user, because the chat template refuses a history that starts with the
    companion. 0 if no such point exists."""
    limit = KEEP_SHARE * budget
    rest = history_chars(messages)
    for k in range(1, len(messages)):
        rest -= len(messages[k - 1].text)
        if rest <= limit and messages[k].from_user:
            return k
    return 0


def newest_within(messages: Sequence[Message], budget: int) -> tuple[Message, ...]:
    """The newest messages that fit ``budget``, starting at a message of the
    user. When a summary cannot be made, the oldest messages are left out
    instead. At least the last message of the user is kept."""
    kept = len(messages)
    total = 0
    start = None
    for k in range(len(messages) - 1, -1, -1):
        total += len(messages[k].text)
        if total > budget and start is not None:
            break
        if messages[k].from_user:
            start = k
        kept = k
    if start is None:
        return tuple(messages[kept:])
    return tuple(messages[start:])


def with_summary(system_prompt: str, summary: Summary | None) -> str:
    """The system text with the summary of the older messages at its end, where
    it changes only when the summary does."""
    if summary is None:
        return system_prompt
    return f"{system_prompt}\n\n{SUMMARY_LEAD}{summary.text}"


def summary_request(previous: str | None, messages: Sequence[Message]) -> str:
    """The text the model summarizes: the earlier summary, if one exists, then
    each message with who said it."""
    lines = []
    if previous:
        lines += [f"Earlier summary: {previous}", ""]
    lines.append("Messages:")
    for m in messages:
        lines.append(f"{'User' if m.from_user else 'Companion'}: {m.text}")
    return "\n".join(lines)


def tidy_summary(text: str) -> str:
    """The summary as it is kept: one paragraph, at most ``SUMMARY_MAX_CHARS``,
    cut after the last whole sentence that fits. Empty if the text is blank."""
    flat = " ".join(text.split())
    if len(flat) <= SUMMARY_MAX_CHARS:
        return flat
    head = flat[:SUMMARY_MAX_CHARS]
    end = max(head.rfind(mark) for mark in _SENTENCE_ENDS)
    return head[: end + 1] if end > 0 else head


def found_text(query: str, messages: Sequence[Message], zone: tzinfo) -> str:
    """What ``search_conversations`` tells the model: each message with its day
    and who said it, or that none holds the words."""
    if not messages:
        return f"No earlier message holds '{query}'."
    parts = []
    for m in messages:
        when = m.created_at.astimezone(zone)
        day = f"{DAYS[when.weekday()][:3]} {when.day} {MONTHS[when.month - 1][:3]}"
        said = m.text
        if len(said) > SEARCH_EXCERPT:
            said = said[: SEARCH_EXCERPT - 1].rstrip() + "…"
        parts.append(f'{day}, {"the user" if m.from_user else "you"}: "{said}"')
    return "Earlier messages: " + "; ".join(parts)


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
