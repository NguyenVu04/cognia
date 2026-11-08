"""The shapes every settings section shares."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import Panel, card
from src.ui.widgets.typography import heading, label, paragraph

MAX_WIDTH = 640


class Section(QWidget):
    """A scrolling section with a heading, an introduction, and a column under
    them. ``error`` is a line for anything that could not be saved."""

    def __init__(self, title: str, intro: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pane = ScrollPane(padding=(28, 32, 32, 32))
        layout.addWidget(self.pane)
        top = self.pane.column
        top.addWidget(heading(title, px=21))
        top.addSpacing(6)
        intro_label = paragraph(
            intro, font=theme.font(14.5), colour=theme.TEXT_SECONDARY, fill=True
        )
        intro_label.setMaximumWidth(MAX_WIDTH)
        top.addWidget(intro_label)
        top.addSpacing(20)
        self.column = QVBoxLayout()
        self.column.setSpacing(12)
        top.addLayout(self.column)
        top.addSpacing(10)
        self.error = paragraph("", font=theme.font(13), colour=theme.DANGER, fill=True)
        self.error.setMaximumWidth(MAX_WIDTH)
        self.error.setVisible(False)
        top.addWidget(self.error)
        top.addStretch(1)

    def showError(self, text: str) -> None:
        """Say what could not be done; "" hides the line."""
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def card(self) -> Panel:
        panel = card(padding=(16, 18, 16, 18))
        panel.setMaximumWidth(MAX_WIDTH)
        self.column.addWidget(panel)
        return panel


def setting_row(title: str, detail: str, control: QWidget) -> tuple[QWidget, QLabel]:
    """A title and a line of detail on the left, a control on the right. Also
    returns the detail label, for owners that change it."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)
    text = QVBoxLayout()
    text.setSpacing(2)
    text.addWidget(label(title, font=theme.font(14.5, 700)))
    words = paragraph(
        detail, font=theme.font(12.5), colour=theme.TEXT_SECONDARY, fill=True
    )
    text.addWidget(words)
    layout.addLayout(text, 1)
    layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    return row, words
