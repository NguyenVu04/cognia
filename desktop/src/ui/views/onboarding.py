"""The two steps after the first choice of a character: desk awareness, then a
few tips. Both can be skipped, and neither is offered again."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.ui import icons, theme
from src.ui.widgets.buttons import Button
from src.ui.widgets.surface import card
from src.ui.widgets.typography import (
    kicker,
    label,
    lede,
    paragraph,
)

TEXT_WIDTH = 560


def _page(step: str, title: str, intro: str) -> tuple[QVBoxLayout, QVBoxLayout]:
    """The outer layout of a step and the column to fill under its heading."""
    outer = QVBoxLayout()
    outer.setContentsMargins(56, 48, 56, 40)
    outer.setSpacing(0)
    outer.addWidget(kicker(step))
    outer.addSpacing(8)
    outer.addWidget(label(title, font=theme.font(28, 800)))
    outer.addSpacing(8)
    outer.addWidget(lede(intro, max_width=TEXT_WIDTH))
    outer.addSpacing(24)
    column = QVBoxLayout()
    column.setSpacing(12)
    outer.addLayout(column)
    outer.addStretch(1)
    return outer, column


def _point(icon_name: str, text: str) -> tuple[QWidget, QLabel]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    layout.addWidget(icons.icon_label(icon_name, 18, theme.ACCENT), 0,
                     Qt.AlignmentFlag.AlignTop)
    words = label(text, font=theme.font(14), wrap=True)
    layout.addWidget(words, 1)
    return row, words


class DeskStep(QWidget):
    """Offer desk awareness once. ``decided`` carries the answer."""

    decided = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer, column = _page(
            "STEP 1 OF 2",
            "Should I notice when you're at your desk?",
            "Then I can suggest a break after a long stretch, say hello when "
            "you're back, and wait while you're busy.",
        )
        self.setLayout(outer)
        panel = card(padding=(18, 20, 18, 20))
        panel.setMaximumWidth(TEXT_WIDTH + 80)
        panel.body().setSpacing(10)
        for icon_name, text in (
            ("eye", "I only notice whether you're around, whether the screen is "
             "locked or you're presenting, and which app is open."),
            ("prohibit", "Never what you type, what's on your screen, or what you "
             "browse."),
            ("clock", "I'll know you're at your desk — never what you're doing "
             "there."),
        ):
            panel.body().addWidget(_point(icon_name, text)[0])
        column.addWidget(panel)
        column.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.yes = Button("Turn it on", variant="primary", icon_name="check")
        self.yes.clicked.connect(lambda: self.decided.emit(True))
        buttons.addWidget(self.yes)
        self.no = Button("Not now")
        self.no.clicked.connect(lambda: self.decided.emit(False))
        buttons.addWidget(self.no)
        buttons.addStretch(1)
        column.addLayout(buttons)
        column.addWidget(
            paragraph(
                "You can change this at any time in Settings › Desk awareness.",
                font=theme.font(12.5), colour=theme.TEXT_FAINT, max_width=TEXT_WIDTH,
            )
        )


class TipsStep(QWidget):
    """Three things worth knowing on the first day."""

    done = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer, column = _page(
            "STEP 2 OF 2",
            "A few things worth knowing",
            "Three things worth knowing on the first day.",
        )
        self.setLayout(outer)
        panel = card(padding=(18, 20, 18, 20))
        panel.setMaximumWidth(TEXT_WIDTH + 80)
        panel.body().setSpacing(12)
        panel.body().addWidget(
            _point("desktop", "Your companion sits at the bottom right of the "
                   "screen. Drag it anywhere; it stays where you put it.")[0]
        )
        talk_row, self.talk = _point("microphone", _talk_text("Ctrl+Alt+Space"))
        panel.body().addWidget(talk_row)
        panel.body().addWidget(
            _point("pause", "Pause everything from the tray icon or the sidebar. "
                   "Closing the window keeps me running in the tray.")[0]
        )
        column.addWidget(panel)
        column.addSpacing(8)
        start = Button("Start talking", variant="primary", icon_name="chat-circle")
        start.clicked.connect(self.done)
        column.addWidget(start, 0, Qt.AlignmentFlag.AlignLeft)

    def setHotkey(self, sequence: str) -> None:
        self.talk.setText(_talk_text(sequence))


def _talk_text(sequence: str) -> str:
    return (
        f"Press {sequence} anywhere to talk instead of typing, then press it again "
        "or stop speaking. You check the words before they are sent."
    )
