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
    #: The conversation, its messages, and the remembered lines that would go
    #: with it.
    conversationDeletionPreviewed = Signal(object, int, int)
    #: A change to a conversation failed; nothing was changed.
    conversationFailed = Signal(str)
    #: The user's message is recorded; a reply is on its way.
    messageAppended = Signal(object)
    #: The reply text, the chip of what was stored, the chip of numbers no
    #: tool gave (each chip may be ""), and the id of the stored reply.
    replyFinished = Signal(str, str, str, str)
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
    #: The companion's face: a VRM preset and its weight from 0 to 1.
    expressionChanged = Signal(str, float)
    #: A gesture to play once, as part of a reply.
    gestureShown = Signal(str)
    #: An exercise to do together: its name and its steps.
    activityStarted = Signal(str, object)
    #: Whether desk awareness is on, and a sentence if it could not be changed
    #: or went off by itself, or "".
    awarenessChanged = Signal(bool, str)

    #: The feeling now and the resting mood, or "" with moods off.
    feelingShown = Signal(str, str)
    #: The character's name and a FeelingExplanation, or None with moods off.
    feelingExplained = Signal(str, object)
    #: The patterns learned, each a Learned.
    learnedShown = Signal(object)
    #: Today's DeskTime and the minutes in each application, both None with
    #: desk awareness off, and the names that are not counted.
    deskShown = Signal(object, object, object)
    speechSettingsShown = Signal(object)
    #: "" when saved, or why not.
    speechSettingsSaved = Signal(str)
    #: Whether replies are said aloud, and the talk key.
    voiceSettingsShown = Signal(bool, str)
    toolServersShown = Signal(object)
    toolServersFailed = Signal(str)
    #: Paused or not, until when as words, and how long the pause lasted.
    pauseChanged = Signal(bool, str, str)
    #: Where the companion was left, as a Placement.
    placementShown = Signal(object)
    #: Whether the first close was already explained.
    closeHintShown = Signal(bool)
    #: The ambient state of the companion: active, waiting or dozing.
    ambientChanged = Signal(str)
    #: A ProactiveMessage to show beside the companion.
    proactiveShown = Signal(object)
    #: The greeting of the day as a stored Message, and why it was said.
    greetingShown = Signal(object, str)
    #: A line from the application in the conversation, never stored.
    noticeShown = Signal(str)
    #: Report the next pause in typing.
    watchForPause = Signal()
    #: The voice of the character and the speed of its mood.
    voiceChanged = Signal(str, float)

    # ── to the model thread ───────────────────────────────────────────────
    askPrepare = Signal(object)
    #: A :class:`~src.app.chat_worker.ReplyRequest`.
    askReply = Signal(object)
    askEmbed = Signal(object)
    #: A :class:`~src.app.chat_worker.SummaryJob`.
    askSummary = Signal(object)
    #: A :class:`~src.app.chat_worker.WordJob`.
    askWord = Signal(object)
    #: The tool servers to use from the next reply.
    addOnsChanged = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.commands: queue.Queue[Command] = queue.Queue(maxsize=QUEUE_SIZE)

    def send(self, command: Command) -> None:
        """Hand a command to the core thread. Safe from any thread."""
        self.commands.put(command)

    def offer(self, command: Command) -> bool:
        """Hand a command over only if the queue has room. For presence, which
        the next sample repeats: a full queue never blocks the sampler."""
        try:
            self.commands.put_nowait(command)
        except queue.Full:
            return False
        return True
