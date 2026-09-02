"""The port through which the companion answers.

"Replying in character" is a domain capability; that it happens to be an AI
model on the far side is an adapter's business. The domain never learns what
runs behind this, which is what lets NFR-09 hold — the model failing is one
adapter raising, not the application breaking.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Protocol

from src.core.models import Message


class ReplyFailed(Exception):
    """The companion could not answer, with a sentence saying what would fix it.

    Carries user-facing text: UC-09 E1 asks the system to say plainly that it
    cannot reply *and what would fix it*, not to print a stack trace.
    """


class Replier(Protocol):
    """Turns a conversation so far into the next thing the companion says."""

    def stream_reply(
        self, system_prompt: str, history: Sequence[Message]
    ) -> Iterator[str]:
        """Yield the reply in pieces, in order, as they become available.

        Only the answer. Whatever reasoning the model does on the way is the
        adapter's to discard. Raises :class:`ReplyFailed` if it cannot answer.
        """
        ...
