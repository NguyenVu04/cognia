"""The port through which the companion answers.

"Replying in character" is a domain capability; that it happens to be an AI
model on the far side is an adapter's business. The domain never learns what
runs behind this, so a failing model is one adapter raising, not the
application breaking: the parts that do not need it keep working.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from typing import Protocol

from src.domain.conversation.models import Message
from src.domain.tools.models import ToolCall, ToolSpec, ToolStarted


class ReplyFailed(Exception):
    """The companion could not answer, with a sentence saying what would fix it.

    Carries user-facing text: when the model is unavailable, the system says
    plainly that it cannot reply *and what would fix it*, never a stack trace.
    """


class Replier(Protocol):
    """Turns a conversation so far into the next thing the companion says."""

    def stream_reply(
        self,
        system_prompt: str,
        history: Sequence[Message],
        turn: str,
        tools: Sequence[ToolSpec] = (),
        run_tool: Callable[[ToolCall], str] | None = None,
    ) -> Iterator[str | ToolStarted]:
        """Yield the reply in pieces, in order, as they become available.

        ``turn`` is layer 4, added to the end of the last user message. Only the
        answer. Whatever reasoning the model does on the way is the adapter's to
        discard. The model may call ``tools``; each call runs ``run_tool`` on the
        caller's thread, after a :class:`ToolStarted`, and the model reads the
        sentence it returns. Raises :class:`ReplyFailed` if it cannot answer.
        """
        ...

    def stream_text(self, system_prompt: str, text: str) -> Iterator[str]:
        """Yield free text for one request with no history, in pieces, such as a
        summary of older messages. Raises :class:`ReplyFailed` if the model
        cannot answer."""
        ...
