"""Talking to the model without freezing the window.

The model call blocks for as long as the model takes, which on a 2B model on a
laptop is seconds. Doing that on the GUI thread would stop the window
repainting, so it happens here instead, on a thread of its own, and the pieces
come back as signals Qt delivers to the GUI thread in order.

This lives in ``app/`` because it touches both Qt and ``infrastructure/``, and
``ui/`` is not allowed to import ``infrastructure/``. It is also the first
threading in this repository: there was no existing pattern to follow.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QObject, Signal, Slot

from src.core.models import Message
from src.core.ports import Replier, ReplyFailed


class ChatWorker(QObject):
    """Runs one reply at a time on the thread it has been moved to."""

    #: One piece of the reply, in order.
    chunk = Signal(str)
    #: The whole reply, once. Not emitted for a cancelled turn.
    finished = Signal(str)
    #: A sentence for the user saying why there is no reply.
    failed = Signal(str)

    def __init__(self, replier: Replier, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._replier = replier
        self._cancelled = False

    def cancel(self) -> None:
        """Abandon the reply in flight.

        Called from the GUI thread while the worker thread is inside the
        stream, so it only sets a flag; the worker notices between pieces.
        UC-09 E2 asks that a discarded reply store nothing, which is why
        ``finished`` is not emitted afterwards.
        """
        self._cancelled = True

    @Slot(str, object)
    def request(self, system_prompt: str, history: Sequence[Message]) -> None:
        self._cancelled = False
        pieces: list[str] = []
        try:
            for piece in self._replier.stream_reply(system_prompt, history):
                if self._cancelled:
                    return
                pieces.append(piece)
                self.chunk.emit(piece)
        except ReplyFailed as error:
            if not self._cancelled:
                self.failed.emit(str(error))
            return
        except Exception as error:  # noqa: BLE001 - the window must not die with it
            if not self._cancelled:
                self.failed.emit(f"I can’t reply just now — {error}")
            return

        if self._cancelled:
            return
        reply = "".join(pieces).strip()
        if reply:
            self.finished.emit(reply)
        else:
            self.failed.emit("The model returned an empty reply. Try again?")
