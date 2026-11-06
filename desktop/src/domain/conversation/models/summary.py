"""The short form of the older part of one conversation.

Only the model reads it: it replaces the messages it covers in the prompt. It is
not a memory, and nothing is kept from it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Summary:
    """``covers`` counts the messages, from the first, that ``text`` replaces.

    Raises ``ValueError`` for a blank text or a count under 1.
    """

    text: str
    covers: int

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("A summary needs text.")
        if self.covers < 1:
            raise ValueError(f"A summary covers 1 message or more, not {self.covers}")
