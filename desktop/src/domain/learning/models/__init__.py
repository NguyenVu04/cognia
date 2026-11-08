"""What the companion learns about how the user works.

The standard library only. A pattern never exists without the events that
show it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

PASSED_OVER_KIND = "passed_over_kind"
REGULAR_ABSENCE = "regular_absence"
SHORT_MESSAGES = "short_messages"

TIMING = "timing"
FREQUENCY = "frequency"
LENGTH = "length"


@dataclass(frozen=True)
class Pattern:
    """A conclusion from counted events. ``parameters`` hold what the rule
    found, such as ``{"kind": "remark"}`` or ``{"hour": "11"}``.

    Raises ``ValueError`` with no evidence.
    """

    rule_id: str
    parameters: tuple[tuple[str, str], ...]
    evidence: tuple[int, ...]
    statement: str

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError("A pattern needs the events that show it.")

    def parameter(self, name: str) -> str:
        return dict(self.parameters).get(name, "")

    @property
    def fingerprint(self) -> str:
        """For example ``regular_absence|hour=11``. The same conclusion always
        gives the same fingerprint."""
        values = ",".join(f"{k}={v}" for k, v in sorted(self.parameters))
        return f"{self.rule_id}|{values}"


@dataclass(frozen=True)
class Adjustment:
    """One change the companion made to itself because of a pattern."""

    aspect: str
    value_before: str
    value_after: str


@dataclass(frozen=True)
class Learned:
    """A stored pattern, its adjustments, and whether they are undone."""

    id: str
    pattern: Pattern
    adjustments: tuple[Adjustment, ...]
    found_at: datetime
    undone: bool = False


@dataclass(frozen=True)
class LearningState:
    """Small running totals, each with the seqs behind it.

    ``passed`` holds, for each kind of message, the seqs of the messages passed
    over at the desk since the last one answered. ``absences`` holds, for each
    hour of the day, the local dates and seqs of absences that began in it.
    ``lengths`` holds the length and seq of the newest user messages.
    ``leaving`` is when and with which event the user left the desk, until
    they come back.
    """

    passed: dict[str, tuple[int, ...]] = field(default_factory=dict)
    absences: dict[int, tuple[tuple[str, int], ...]] = field(default_factory=dict)
    lengths: tuple[tuple[int, int], ...] = ()
    leaving: tuple[datetime, int] | None = None


__all__ = [
    "FREQUENCY",
    "LENGTH",
    "PASSED_OVER_KIND",
    "REGULAR_ABSENCE",
    "SHORT_MESSAGES",
    "TIMING",
    "Adjustment",
    "Learned",
    "LearningState",
    "Pattern",
]
