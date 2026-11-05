"""Talking to the model without freezing the window.

A model call blocks for as long as the model takes, which on a small model on a
laptop is seconds. Doing that on the GUI thread would stop the window
repainting, so it happens here instead, on a thread of its own, and the results
come back as signals Qt delivers to the GUI thread in order.

One turn has two requests. ``prepare`` finds what the reply draws on and what
the message holds worth keeping. ``request`` streams the reply. Nothing here
touches the database: the GUI thread holds it.

This lives in ``app/`` because it touches both Qt and the model ports, and
``ui/`` is not allowed to reach the model.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from PySide6.QtCore import QObject, Signal, Slot

from src.domain.conversation import rules as conversation_rules
from src.domain.conversation.models import Interpretation, Message
from src.domain.memory import rules as memory_rules
from src.domain.memory.models import Calibration, Entry, Scored, Vector
from src.domain.ports import (
    Embedder,
    EmbedFailed,
    Interpreter,
    InterpretFailed,
    Replier,
    ReplyFailed,
)


@dataclass(frozen=True)
class TurnRequest:
    """One message of the user, and what the worker needs to prepare for it.

    ``history`` ends with that message. ``crisis`` means the tripwire fired,
    so nothing from the message is kept.
    """

    turn_id: int
    system_prompt: str
    history: tuple[Message, ...]
    entries: tuple[Entry, ...]
    crisis: bool
    today: date
    now: datetime
    calibration: Calibration


@dataclass(frozen=True)
class Prepared:
    """What the reply draws on, and what the message holds worth keeping.

    ``found`` is ``None`` when the message was not interpreted. ``vectors``
    holds the vector of each candidate line by its tidied text.
    """

    turn_id: int
    recalled: tuple[Scored, ...]
    found: Interpretation | None
    vectors: Mapping[str, Vector] = field(default_factory=dict)


class ChatWorker(QObject):
    """Runs one model request at a time on the thread it has been moved to."""

    #: One piece of the reply, in order.
    chunk = Signal(str)
    #: The whole reply, once. Not emitted for a cancelled turn.
    finished = Signal(str)
    #: A sentence for the user saying why there is no reply.
    failed = Signal(str)
    #: A :class:`Prepared`, always, even when the model could not help.
    prepared = Signal(object)
    #: A list of ``(entry, vector)`` pairs. Not emitted if no vector was made.
    embedded = Signal(object)

    def __init__(
        self,
        replier: Replier,
        interpreter: Interpreter,
        embedder: Embedder,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._replier = replier
        self._interpreter = interpreter
        self._embedder = embedder
        self._cancelled = False

    def cancel(self) -> None:
        """Abandon the reply in flight.

        Called from the GUI thread while the worker thread is inside the
        stream, so it only sets a flag; the worker notices between pieces.
        A reply the user discarded must store nothing, which is why
        ``finished`` is not emitted afterwards.
        """
        self._cancelled = True

    @Slot(object)
    def prepare(self, request: TurnRequest) -> None:
        """Recall what the reply draws on, then interpret the message. A model
        that fails only leaves out its part: the reply still comes."""
        message = request.history[-1].text
        query = self._vector(message)
        recalled = memory_rules.recall(
            request.entries, query, request.now, request.calibration
        )
        if request.crisis:
            self.prepared.emit(Prepared(request.turn_id, recalled, None))
            return
        known = memory_rules.known(request.entries, query)
        found = self._interpret(request, [entry.text for entry in known])
        vectors: dict[str, Vector] = {}
        if found is not None:
            lines = [memory_rules.tidy(f) for f in found.facts]
            lines += [memory_rules.tidy(c.text) for c in found.commitments]
            lines = [line for line in dict.fromkeys(lines) if line]
            try:
                vectors = dict(zip(lines, self._embedder.embed(lines)))
            except EmbedFailed:
                vectors = {}
        self.prepared.emit(Prepared(request.turn_id, recalled, found, vectors))

    @Slot(str, object, str)
    def request(
        self, system_prompt: str, history: Sequence[Message], turn: str
    ) -> None:
        self._cancelled = False
        pieces: list[str] = []
        try:
            for piece in self._replier.stream_reply(system_prompt, history, turn):
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

    @Slot(object)
    def embed(self, entries: Sequence[Entry]) -> None:
        """Compute the vectors that are missing. On failure they keep waiting."""
        if not entries:
            return
        try:
            vectors = self._embedder.embed([entry.text for entry in entries])
        except EmbedFailed:
            return
        self.embedded.emit(list(zip(entries, vectors)))

    def _vector(self, text: str) -> Vector | None:
        try:
            return self._embedder.embed([text])[0]
        except EmbedFailed:
            return None

    def _interpret(
        self, request: TurnRequest, known: list[str]
    ) -> Interpretation | None:
        instruction = conversation_rules.interpretation_instruction(
            request.today, known
        )
        try:
            data = self._interpreter.interpret(
                request.system_prompt,
                request.history,
                instruction,
                conversation_rules.INTERPRETATION_SCHEMA,
            )
            return conversation_rules.read_interpretation(data)
        except (InterpretFailed, ValueError):
            return None
