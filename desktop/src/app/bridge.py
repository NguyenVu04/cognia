"""The only place where Qt and the core thread meet.

Into the core: one bounded queue of commands, read by one thread. Out of the
core: Qt signals. The core emits them on its own thread, and Qt delivers each
one queued on the thread of the object it is connected to, so the GUI and the
model thread each receive their data on their own thread, in order.
"""

from __future__ import annotations

import queue

from PySide6.QtCore import QObject, Signal

from src.app.commands import Command

# A command is never dropped: the queue fills only if the core thread stalls.
QUEUE_SIZE = 1024


class Bridge(QObject):
    """Signals from the core, and :meth:`send` into it.

    Payloads are frozen domain values or lists of them, never live objects.
    """

    # ── to the GUI ────────────────────────────────────────────────────────
    #: The first data is sent; views may stop waiting.
    ready = Signal()
    #: The version in force or ``None``, the earlier versions with the moment
    #: each stopped, the day of the first choice, and a history error or "".
    characterShown = Signal(object, object, object, str)
    #: The ready-made characters, the template in force or ``None``, and an
    #: error or "". The GUI shows the choice of a character.
    templatesShown = Signal(object, object, str)
    #: A screen to show after a choice of character: "chat" or "character".
    screenRequested = Signal(str)
    characterFailed = Signal(str)
    conversationLoaded = Signal(object)
    #: Every conversation, and the id of the one in use.
    conversationsChanged = Signal(object, str)
    #: The user's message is recorded; a reply is on its way.
    messageAppended = Signal(object)
    #: The reply text and the chip under it, or "".
    replyFinished = Signal(str, str)
    #: The reply text, and why it could not be kept.
    replyNotSaved = Signal(str, str)
    replyFailed = Signal(str)
    #: The remembered items.
    memoryShown = Signal(object)
    memoryFailed = Signal(str)
    #: The level, the rows of each group, and the character's name or ``None``.
    erasurePreviewed = Signal(object, object, object)
    erasureReported = Signal(object)
    #: A step failed in a way nobody expected; nothing of it was kept. The
    #: sentence, and the command that failed, or ``None`` if the start failed.
    coreFailed = Signal(str, object)

    # ── to the model thread ───────────────────────────────────────────────
    askPrepare = Signal(object)
    askReply = Signal(str, object, str)
    askEmbed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.commands: queue.Queue[Command] = queue.Queue(maxsize=QUEUE_SIZE)

    def send(self, command: Command) -> None:
        """Hand a command to the core thread. Safe from any thread."""
        self.commands.put(command)
