"""The shape every dialog shares: a title, some lines of text, and a row of
buttons, on a frameless card that Esc closes."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.widgets.frameless import FramelessWindow
from src.ui.widgets.layout import centre_on, clear
from src.ui.widgets.typography import label, paragraph


class DialogWindow(FramelessWindow):
    """A modal card. Subclasses fill :attr:`content` and :attr:`buttons`."""

    def __init__(
        self, title: str, *, width: int = 460, parent: QWidget | None = None
    ) -> None:
        super().__init__(fill=theme.BG_CARD, flags=Qt.WindowType.Dialog, parent=parent)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle(title)
        self.body.setFixedWidth(width)
        self._text_width = width - 56
        frame = self.body.body()
        frame.setContentsMargins(28, 24, 28, 22)
        self.content = QVBoxLayout()
        self.content.setSpacing(0)
        frame.addLayout(self.content)
        frame.addSpacing(20)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(10)
        frame.addLayout(self.buttons)

    def clear(self) -> None:
        clear(self.content)
        clear(self.buttons)

    def title(self, text: str) -> None:
        self.content.addWidget(label(text, font=theme.font(19, 700)))
        self.content.addSpacing(10)

    def text(self, text: str, *, colour=theme.TEXT_SECONDARY) -> None:
        self.content.addWidget(
            paragraph(
                text,
                font=theme.font(13.5),
                colour=colour,
                max_width=self._text_width,
            )
        )
        self.content.addSpacing(6)

    def add_button(
        self, button: QPushButton, action: Callable[[], None]
    ) -> QPushButton:
        button.clicked.connect(lambda: action())
        self.buttons.addWidget(button)
        return button

    def centre_on(self, widget: QWidget) -> None:
        self.adjustSize()
        centre_on(self, widget)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
