"""The companion on the desktop, joined to the core: its character, face,
gestures, waiting and dozing, exercises, the bubble of what it says on its own,
and where it stands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint, Slot

from src.app.commands import (
    ActivityEnded,
    CompanionMoved,
    CompanionShown,
    RespondToMessage,
    SetKind,
    StartActivity,
    UndoLearned,
)
from src.domain.speech.models import MessageKind
from src.ui.windows.companion_window import HIDDEN, PAUSED, SHOWN

if TYPE_CHECKING:
    from src.app.application import Cognia

MOVED = (
    "I moved {name} back onto the screen, since the place where you left them is gone."
)
NOT_DRAWN = (
    "I can't show {name} on the desktop right now: {reason} Everything else "
    "still works."
)


class CompanionWiring(QObject):
    def __init__(self, cognia: Cognia) -> None:
        super().__init__()
        self.c = cognia
        self.hidden = False
        self.paused = False
        self._name = ""
        self._placed = False
        companion, bridge, send = cognia.companion, cognia.bridge, cognia.bridge.send

        bridge.expressionChanged.connect(companion.setExpression)
        bridge.gestureShown.connect(companion.playGesture)
        bridge.ambientChanged.connect(companion.setAmbient)
        bridge.activityStarted.connect(self._activity_started)
        bridge.proactiveShown.connect(self._proactive)
        bridge.placementShown.connect(self._place)
        bridge.pauseChanged.connect(self._pause_changed)
        companion.activityEnded.connect(lambda name, s: send(ActivityEnded(name, s)))
        companion.moved.connect(lambda x, y, screen: send(CompanionMoved(x, y, screen)))
        companion.hideRequested.connect(self.toggle)
        companion.drawingFailed.connect(self._failed)
        for bubble in (companion.bubble, cognia.window.bubble):
            bubble.responded.connect(lambda did, r: send(RespondToMessage(did, r)))
            bubble.activityRequested.connect(lambda name: send(StartActivity(name)))
            bubble.dontSendRequested.connect(
                lambda kind: send(SetKind(MessageKind(kind), False))
            )
            bubble.undoRequested.connect(lambda lid: send(UndoLearned(lid)))
            bubble.settingsRequested.connect(self.c.screens.open_speaking_up)
        # A bound slot, so Qt calls it on this thread, never the model thread.
        cognia.worker.toolStarted.connect(self._tool_started)
        cognia.worker.toolEnded.connect(companion.endThink)

    @Slot(str)
    def _tool_started(self, _working: str) -> None:
        self.c.companion.startThink()

    def set_character(self, version) -> None:
        self._name = version.name if version else ""
        if version is None:
            self.c.companion.setDrawingState(HIDDEN)
            return
        self.c.companion.setAppearance(version.appearance_id)
        self._refresh()

    def _refresh(self) -> None:
        if not self._placed or not self._name:
            return
        drawing = PAUSED if self.paused else HIDDEN if self.hidden else SHOWN
        self.c.companion.setDrawingState(drawing)
        self.c.sync_companion_labels(self.hidden, self._name)

    def toggle(self) -> None:
        """Hide the companion, or show it again where it was."""
        self.hidden = not self.hidden
        self.c.bridge.send(CompanionShown(not self.hidden))
        self._refresh()

    @Slot(object)
    def _place(self, placement) -> None:
        self.hidden = placement.hidden
        position = None
        if placement.x is not None and placement.y is not None:
            position = QPoint(placement.x, placement.y)
        if self.c.companion.place(position) and self._name:
            self.c.window.chat.showNotice(MOVED.format(name=self._name))
        self._placed = True
        self._refresh()

    @Slot(bool, str, str)
    def _pause_changed(self, paused: bool, until: str, lasted: str) -> None:
        self.paused = paused
        self._refresh()

    @Slot(str, object)
    def _activity_started(self, name: str, steps) -> None:
        companion = self.c.companion
        if not companion.isVisible():
            # Nobody can do an exercise with a companion that is not on screen.
            self.c.bridge.send(ActivityEnded(name, 0))
            return
        companion.playActivity(name, steps)

    @Slot(object)
    def _proactive(self, message) -> None:
        """Say it beside the companion, or in the window while it is hidden."""
        companion, window = self.c.companion, self.c.window
        if message is None:
            companion.hideBubble()
            window.bubble.hide()
            return
        if companion.isVisible():
            companion.showBubble(message)
        else:
            window.showHeldMessage(message)
        self.c.voice.say_text(message.text)

    @Slot(str)
    def _failed(self, reason: str) -> None:
        self.c.window.chat.showNotice(NOT_DRAWN.format(name=self._name, reason=reason))
