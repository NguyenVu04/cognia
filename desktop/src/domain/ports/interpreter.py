"""The port through which a message is interpreted.

The answer follows a JSON schema that the caller gives, so it is a plain
mapping here. The domain reads it and refuses a wrong shape.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from src.domain.conversation.models import Message


class InterpretFailed(Exception):
    """The message could not be interpreted, with a sentence saying why."""


class Interpreter(Protocol):
    def interpret(
        self,
        system_prompt: str,
        history: Sequence[Message],
        turn: str,
        schema: Mapping[str, object],
    ) -> Mapping[str, object]:
        """The answer to ``turn``, added to the last user message, as an object
        that fits ``schema``. Raises :class:`InterpretFailed`."""
        ...
