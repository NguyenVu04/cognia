"""The pure tools, and the checks around every tool.

Each function returns a sentence for the model, never an empty value, so the
model has something true to say even when a tool cannot help.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal, DivisionByZero, InvalidOperation, Overflow, localcontext
from urllib.parse import quote_plus, urlsplit

from src.domain.conversation.rules import DAYS, MONTHS, long_date
from src.domain.ports.dictionary import Sense
from src.domain.tools.models import ActivityStep, ToolResult

TOOL_FAILED = "I couldn't check that just now."
SEARCH_URL = "https://duckduckgo.com/?q="

NOT_ARITHMETIC = "I can't work that out: it is not an arithmetic expression."
DIVIDES_BY_ZERO = "I can't work that out: it divides by zero."
TOO_LARGE = "I can't work that out: the numbers are too large."
NOT_ASKED = (
    "Not opened: the user did not ask to open a page. You may offer to open it."
)
NOT_OPENABLE = "Not opened: only http and https pages can be opened."

# Long input or huge powers could keep the model thread busy.
_MAX_EXPRESSION = 200
_MAX_EXPONENT = 100
_MAX_DIGITS = 60
_ALIASES = {"×": "*", "÷": "/", "−": "-", "**": "^"}
_TOKEN = re.compile(r"\s*(\d+(?:\.\d*)?|\.\d+|[-+*/%^()])")

_LENGTH_METRES = {
    "mm": Decimal("0.001"), "cm": Decimal("0.01"), "m": Decimal(1),
    "km": Decimal(1000), "in": Decimal("0.0254"), "ft": Decimal("0.3048"),
    "yd": Decimal("0.9144"), "mi": Decimal("1609.344"),
}
_WEIGHT_KILOGRAMS = {
    "g": Decimal("0.001"), "kg": Decimal(1), "oz": Decimal("0.028349523125"),
    "lb": Decimal("0.45359237"),
}
_TEMPERATURES = ("c", "f", "k")

# Words that ask for a page to be opened. Asking a question is not asking for a
# browser, so a model that opens one unasked is refused.
_OPEN_WORDS = re.compile(r"\b(open|show me|look (?:it |that )?up|search)\b")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


# ── calculate ────────────────────────────────────────────────────────────


class _NotArithmetic(Exception):
    pass


def calculate(expression: str) -> str:
    """``expression`` and its exact value, or why it cannot be worked out."""
    text = expression.strip()
    if not text or len(text) > _MAX_EXPRESSION:
        return NOT_ARITHMETIC
    for alias, symbol in _ALIASES.items():
        text = text.replace(alias, symbol)
    try:
        tokens = _tokens(text)
        with localcontext() as context:
            context.prec = _MAX_DIGITS
            context.traps[Overflow] = True
            parser = _Parser(tokens)
            value = parser.expression()
            if parser.position != len(tokens):
                raise _NotArithmetic
            if abs(value) >= Decimal(10) ** _MAX_DIGITS:
                return TOO_LARGE
            shown = _plain(value)
    except ZeroDivisionError:
        return DIVIDES_BY_ZERO
    except (DivisionByZero, InvalidOperation) as error:
        if isinstance(error, DivisionByZero):
            return DIVIDES_BY_ZERO
        return NOT_ARITHMETIC
    except (Overflow, OverflowError):
        return TOO_LARGE
    except _NotArithmetic:
        return NOT_ARITHMETIC
    return f"{expression.strip()} = {shown}"


def _tokens(text: str) -> list[str]:
    tokens, position = [], 0
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None:
            if text[position:].strip():
                raise _NotArithmetic
            break
        tokens.append(match.group(1))
        position = match.end()
    return tokens


class _Parser:
    """expression := term (("+" | "-") term)*
    term := unary (("*" | "/" | "%") unary)*
    unary := ("-" | "+") unary | power
    power := primary ("^" unary)?
    primary := number | "(" expression ")"

    A power binds before a sign, so -3^2 is -9.
    """

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.position = 0

    def _peek(self) -> str | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def _take(self) -> str:
        token = self._peek()
        if token is None:
            raise _NotArithmetic
        self.position += 1
        return token

    def expression(self) -> Decimal:
        value = self.term()
        while self._peek() in ("+", "-"):
            value = value + self.term() if self._take() == "+" else value - self.term()
        return value

    def term(self) -> Decimal:
        value = self.unary()
        while self._peek() in ("*", "/", "%"):
            operator, right = self._take(), self.unary()
            if operator == "*":
                value *= right
            elif right == 0:
                raise ZeroDivisionError
            elif operator == "/":
                value /= right
            else:
                value %= right
        return value

    def unary(self) -> Decimal:
        if self._peek() == "-":
            self._take()
            return -self.unary()
        if self._peek() == "+":
            self._take()
            return self.unary()
        return self.power()

    def power(self) -> Decimal:
        base = self.primary()
        if self._peek() != "^":
            return base
        self._take()
        exponent = self.unary()
        if abs(exponent) > _MAX_EXPONENT:
            raise Overflow
        if base == 0 and exponent < 0:
            raise ZeroDivisionError
        if exponent == exponent.to_integral_value():
            return base ** int(exponent)
        # A fraction of a power of a negative number has no real value, which
        # Decimal reports as an invalid operation.
        return base**exponent

    def primary(self) -> Decimal:
        token = self._take()
        if token == "(":
            value = self.expression()
            if self._take() != ")":
                raise _NotArithmetic
            return value
        if token[0].isdigit() or token[0] == ".":
            return Decimal(token)
        raise _NotArithmetic


def _plain(value: Decimal) -> str:
    """The value with no exponent and no trailing zeros. A fraction keeps 15
    significant digits, more than anyone reads and few enough to repeat."""
    if value == value.to_integral_value():
        return str(value.quantize(Decimal(1)))
    return format(Decimal(format(value, ".15g")).normalize(), "f")


# ── date ─────────────────────────────────────────────────────────────────


def date_answer(arguments: Mapping[str, object], now: datetime) -> str:
    """Today, a weekday, the days between two dates, or a date some days on,
    all counted from the time of the turn."""
    op = arguments.get("op")
    today = now.date()
    try:
        when = _date(arguments.get("date"), today)
        if op == "today":
            return f"Today is {long_date(today)}."
        if op == "weekday":
            return f"{_day(when)} is a {DAYS[when.weekday()]}."
        if op == "between":
            other = _date(arguments.get("other"), today)
            first, last = sorted((when, other))
            days = (last - first).days
            return f"From {_day(first)} to {_day(last)} is {_days(days)}."
        if op == "add_days":
            days = arguments.get("days")
            if isinstance(days, bool) or not isinstance(days, int):
                return TOOL_FAILED
            later = when + timedelta(days=days)
            direction = "after" if days >= 0 else "before"
            return f"{_days(abs(days))} {direction} {_day(when)} is {long_date(later)}."
    except _BadDate as error:
        return f"I can't read the date '{error}'. Dates are YYYY-MM-DD."
    except OverflowError:
        return TOOL_FAILED
    return TOOL_FAILED


class _BadDate(Exception):
    pass


def _date(value: object, today: date) -> date:
    if value is None or value == "":
        return today
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise _BadDate(str(value)) from error


def _day(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def _days(count: int) -> str:
    return "1 day" if count == 1 else f"{count} days"


# ── convert_units ────────────────────────────────────────────────────────


def convert(value: object, source: str, target: str) -> str:
    """``value`` in ``source`` units as ``target`` units, from a fixed table."""
    failed = f"I can't convert {source} to {target}."
    if isinstance(value, bool) or not isinstance(value, int | float):
        return failed
    a, b = _unit(source), _unit(target)
    amount = Decimal(str(value))
    if a in _LENGTH_METRES and b in _LENGTH_METRES:
        result = amount * _LENGTH_METRES[a] / _LENGTH_METRES[b]
    elif a in _WEIGHT_KILOGRAMS and b in _WEIGHT_KILOGRAMS:
        result = amount * _WEIGHT_KILOGRAMS[a] / _WEIGHT_KILOGRAMS[b]
    elif a in _TEMPERATURES and b in _TEMPERATURES:
        result = _from_kelvin(_to_kelvin(amount, a), b)
    else:
        return failed
    shown = _plain(result.quantize(Decimal("0.01")))
    return f"{_plain(amount)} {source.strip()} is {shown} {target.strip()}."


def _unit(name: str) -> str:
    return name.strip().casefold().removeprefix("°").removeprefix("degrees ")


def _to_kelvin(amount: Decimal, unit: str) -> Decimal:
    if unit == "c":
        return amount + Decimal("273.15")
    if unit == "f":
        return (amount - 32) * 5 / 9 + Decimal("273.15")
    return amount


def _from_kelvin(kelvin: Decimal, unit: str) -> Decimal:
    if unit == "c":
        return kelvin - Decimal("273.15")
    if unit == "f":
        return (kelvin - Decimal("273.15")) * 9 / 5 + 32
    return kelvin


# ── open_in_browser ──────────────────────────────────────────────────────


def asked_to_open(user_text: str) -> bool:
    """Whether the user's message asks for a page or a search to be opened."""
    return _OPEN_WORDS.search(user_text.casefold()) is not None


def browser_url(arguments: Mapping[str, object]) -> str | None:
    """The address to open: an http or https page, or a search. ``None`` for
    anything else, such as a ``javascript:`` or ``file:`` address."""
    url = arguments.get("url")
    if isinstance(url, str) and url.strip():
        parts = urlsplit(url.strip())
        if parts.scheme in ("http", "https") and parts.netloc:
            return url.strip()
        return None
    search = arguments.get("search")
    if isinstance(search, str) and search.strip():
        return SEARCH_URL + quote_plus(search.strip())
    return None


def opened(url: str, arguments: Mapping[str, object]) -> str:
    """What the model is told after a page opened."""
    search = arguments.get("search")
    if url.startswith(SEARCH_URL) and isinstance(search, str):
        return f"Opened a search for '{search.strip()}' in the user's browser."
    return f"Opened {url} in the user's browser."


# ── exercises done together ──────────────────────────────────────────────

# The steps of each exercise. Start values, about a minute each.
ACTIVITIES: dict[str, tuple[ActivityStep, ...]] = {
    "breathing": (
        ActivityStep("breathe in", 4),
        ActivityStep("hold", 4),
        ActivityStep("breathe out", 6),
    )
    * 5,
    "stretch": (
        ActivityStep("reach up", 20),
        ActivityStep("roll your shoulders", 20),
        ActivityStep("turn your head slowly", 20),
        ActivityStep("stretch your wrists", 20),
    ),
}
_STARTED = {"breathing": "breathing together", "stretch": "stretching together"}
ALREADY_RUNNING = "Not started: an exercise is already running."


def activity(name: str) -> tuple[ActivityStep, ...]:
    """The steps of the exercise ``name``. Raises ``ValueError`` for another."""
    steps = ACTIVITIES.get(name)
    if steps is None:
        raise ValueError(f"No exercise is called {name!r}.")
    return steps


def started(name: str) -> str:
    """What the model is told when the exercise begins."""
    seconds = sum(step.seconds for step in activity(name))
    return f"Started: {_STARTED[name]} for {seconds} seconds."


# ── define_word ──────────────────────────────────────────────────────────


def candidates(word: str) -> tuple[str, ...]:
    """``word`` and the forms it may come from, so "studies" finds "study" and
    "baked" finds "bake". The word itself is tried first."""
    w = word.strip().casefold()
    found = [w]
    if w.endswith("ies") and len(w) > 4:
        found.append(w[:-3] + "y")
    if w.endswith("es") and len(w) > 3:
        found.append(w[:-2])
    if w.endswith("s") and len(w) > 2:
        found.append(w[:-1])
    if w.endswith("ed") and len(w) > 3:
        found += [w[:-2], w[:-1]]
    if w.endswith("ing") and len(w) > 4:
        found += [w[:-3], w[:-3] + "e"]
    return tuple(dict.fromkeys(found))


def define_text(word: str, senses: Sequence[Sense]) -> str:
    """What ``define_word`` tells the model about ``word``."""
    if not senses:
        return f"The dictionary on this machine has no entry for '{word}'."
    return "; ".join(f"{word} ({s.pos}): {s.definition}" for s in senses)


# ── the number check ─────────────────────────────────────────────────────


def numbers(text: str) -> tuple[str, ...]:
    """The numbers written in digits in ``text``, in a canonical form:
    "1,200" is "1200", "3.50" is "3.5", and "10:30" is "10" and "30"."""
    found = []
    for raw in _NUMBER.findall(text):
        plain = raw.replace(",", "")
        if "." in plain:
            plain = plain.rstrip("0").rstrip(".")
        found.append(plain or "0")
    return tuple(found)


def unchecked_numbers(reply: str, sources: Sequence[str]) -> tuple[str, ...]:
    """The numbers of ``reply`` that none of ``sources`` holds, each once."""
    known = {n for source in sources for n in numbers(source)}
    return tuple(dict.fromkeys(n for n in numbers(reply) if n not in known))


def number_note(unchecked: Sequence[str], results: Sequence[ToolResult]) -> str:
    """The chip under a reply whose numbers did not come from what was checked.
    Empty if every number came from somewhere."""
    if not unchecked:
        return ""
    found = "; ".join(r.text for r in results)
    return f"Not from what I checked: {', '.join(unchecked)} · I found: {found}"
