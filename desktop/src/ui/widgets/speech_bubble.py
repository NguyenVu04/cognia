"""The bubble of a message the companion says on its own.

Every such message carries a way to ask why it appeared and a way to switch its
kind off in one press. A break suggestion also offers to take the break, to
breathe together, to postpone it, or to stop them for today; an adjustment
offers its undo.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from src.domain.speech.models import (
    KIND_LABELS,
    MessageKind,
    ProactiveMessage,
    Response,
)
from src.ui import theme
from src.ui.widgets.buttons import Button, IconButton
from src.ui.widgets.layout import clear
from src.ui.widgets.surface import Panel
from src.ui.widgets.typography import kicker, paragraph

WIDTH = 320
TEXT_WIDTH = WIDTH - 36


class SpeechBubble(QWidget):
    #: The decision id and what the user did with the message.
    responded = Signal(str, str)
    #: The user wants to do an exercise now, such as "breathing".
    activityRequested = Signal(str)
    #: Switch this kind of message off, with no question asked.
    dontSendRequested = Signal(str)
    #: Open the settings that produced the message.
    settingsRequested = Signal()
    #: Undo the adjustment that the message announced: the pattern id.
    undoRequested = Signal(str)
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(WIDTH)
        self.message: ProactiveMessage | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = Panel(
            fill=theme.BG_BUBBLE, ring=theme.ACCENT, radius=16, padding=(12, 16, 12, 16)
        )
        outer.addWidget(panel)
        head = QHBoxLayout()
        self.kind = kicker("")
        head.addWidget(self.kind)
        head.addStretch(1)
        close = IconButton("x", "Close", px=13, box=26)
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.clicked.connect(lambda: self._respond(Response.DISMISSED))
        head.addWidget(close)
        panel.body().addLayout(head)
        panel.body().addSpacing(4)
        self.text = paragraph("", font=theme.font(14.5), max_width=TEXT_WIDTH)
        panel.body().addWidget(self.text)
        panel.body().addSpacing(8)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(6)
        panel.body().addLayout(self.actions)
        self.reasons = QVBoxLayout()
        self.reasons.setSpacing(4)
        panel.body().addLayout(self.reasons)
        panel.body().addSpacing(6)
        links = QHBoxLayout()
        links.setSpacing(4)
        self.why = Button("Why?", size="small", variant="ghost", icon_name="question")
        self.why.clicked.connect(self._toggle_why)
        links.addWidget(self.why)
        self.dont_send = Button(
            "Don’t send this kind again", size="small", variant="ghost"
        )
        self.dont_send.clicked.connect(self._dont_send)
        links.addWidget(self.dont_send)
        links.addStretch(1)
        panel.body().addLayout(links)
        for button in self.findChildren(Button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def showMessage(self, message: ProactiveMessage) -> None:
        self.message = message
        self.kind.setText(KIND_LABELS[message.kind][0].upper())
        self.text.setText(message.text)
        self.text.setFixedWidth(TEXT_WIDTH)
        self.text.setMinimumHeight(self.text.heightForWidth(TEXT_WIDTH))
        clear(self.reasons)
        clear(self.actions)
        if message.kind is MessageKind.BREAK:
            self._action("Take a break", Response.TAKEN, primary=True)
            self._action("Breathe with me", Response.TAKEN, activity="breathing")
            self._action("Later", Response.POSTPONED)
            self._action("Not today", Response.SILENCED)
        elif message.kind is MessageKind.ADJUSTMENT and message.ref_id:
            undo = Button("Undo", size="small", icon_name="arrow-counter-clockwise")
            undo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            undo.clicked.connect(self._undo)
            self.actions.addWidget(undo)
        self.actions.addStretch(1)
        self.adjustSize()

    def reasonLines(self) -> list[str]:
        return list(self.message.reasons) if self.message else []

    def _action(
        self,
        text: str,
        response: Response,
        *,
        primary: bool = False,
        activity: str = "",
    ) -> None:
        button = Button(
            text, size="small", variant="primary" if primary else "secondary"
        )
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda: self._respond(response, activity))
        self.actions.addWidget(button)

    def _toggle_why(self) -> None:
        if self.reasons.count():
            clear(self.reasons)
        elif self.message is not None:
            for line in self.message.reasons:
                self.reasons.addWidget(
                    paragraph(
                        f"• {line}",
                        font=theme.font(12.5),
                        colour=theme.TEXT_SECONDARY,
                        max_width=TEXT_WIDTH,
                    )
                )
            change = Button(
                "Change this setting",
                size="small",
                variant="ghost",
                icon_name="gear-six",
            )
            change.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            change.clicked.connect(self.settingsRequested)
            self.reasons.addWidget(change, 0, Qt.AlignmentFlag.AlignLeft)
        self.adjustSize()
        if self.window() is not self:
            self.window().adjustSize()

    def _respond(self, response: Response, activity: str = "") -> None:
        if self.message is not None:
            self.responded.emit(self.message.decision_id, response.value)
        if activity:
            self.activityRequested.emit(activity)
        self._close()

    def _dont_send(self) -> None:
        if self.message is not None:
            self.dontSendRequested.emit(self.message.kind.value)
            self.responded.emit(self.message.decision_id, Response.DISMISSED.value)
        self._close()

    def _undo(self) -> None:
        if self.message is not None:
            self.undoRequested.emit(self.message.ref_id)
            self.responded.emit(self.message.decision_id, Response.ANSWERED.value)
        self._close()

    def _close(self) -> None:
        """The owner hides the bubble when it hears ``closed``."""
        self.message = None
        self.closed.emit()
