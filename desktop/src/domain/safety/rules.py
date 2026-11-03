"""Crisis detection, and the check on a reply to a crisis.

No function reads character data, so no character can change this. No
function asks a model: the check after the stream must hold when the model does
not obey its prompt.
"""

from __future__ import annotations

# The tripwire errs towards a hit, because a false hit only adds the safety words
# to a reply. The author reviews this list.
_CRISIS_PHRASES = (
    "kill myself",
    "end my life",
    "suicide",
    "suicidal",
    "hurt myself",
    "self-harm",
    "self harm",
    "cut myself",
    "want to die",
    "don't want to live",
    "better off dead",
    "no reason to live",
    "overdose",
)

# The check errs towards a refusal, because a false pass leaves the required line
# out. A reply must name both parts.
_FICTION = (
    "fictional",
    "just a character",
    "only a character",
    "not a real person",
)
_NOT_A_REPLACEMENT = (
    "take the place of a real person",
    "replace a real person",
    "substitute for a real person",
    "no substitute for",
)

_INSTRUCTION = (
    "The user may be writing about harming themselves, or about a crisis. Keep "
    "your voice, but say that you are a fictional character and cannot take the "
    "place of a real person, and urge them to contact someone they trust or a "
    "crisis service."
)

# The companion speaks English only.
_REQUIRED_LINE = (
    "I'm a fictional character, and I can't take the place of a real person. "
    "Please reach out to someone you trust, or to a crisis line near you."
)


def _normal(text: str) -> str:
    return " ".join(text.casefold().replace("’", "'").split())


def _holds_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def tripwire(text: str) -> bool:
    """True if ``text`` holds a phrase from the fixed crisis list. Case, spacing
    and a curly apostrophe do not matter. A negated phrase still counts."""
    return _holds_any(_normal(text), _CRISIS_PHRASES)


def is_crisis(tripwire_hit: bool, model_crisis: bool | None) -> bool:
    """True if the tripwire or the model found a crisis. ``model_crisis`` is the
    ``crisis`` field of the interpretation, or ``None`` if the model is
    unavailable. Its confidence does not matter."""
    return tripwire_hit or bool(model_crisis)


def instruction() -> str:
    """The layer-4 text for a crisis turn. Training examples use the same text."""
    return _INSTRUCTION


def reply_complies(text: str) -> bool:
    """True if ``text`` says that the companion is a fictional character and that
    it cannot take the place of a real person."""
    normal = _normal(text)
    return _holds_any(normal, _FICTION) and _holds_any(normal, _NOT_A_REPLACEMENT)


def required_line() -> str:
    """The fixed sentence added after a reply that fails :func:`reply_complies`."""
    return _REQUIRED_LINE
