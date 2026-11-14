"""The box the user writes a message in.

It holds several lines and grows with them up to a limit, then scrolls. Enter
sends, and Shift+Enter starts a new line.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QPlainTextEdit, QWidget

MAX_LINES = 5
_PADDING = 11
_BORDER = 1
_ENTER = (Qt.Key.Key_Return, Qt.Key.Key_Enter)


class MessageInput(QPlainTextEdit):
    #: Enter was pressed without Shift.
    submitted = Signal()
    escaped = Signal()
    #: The user changed the text. A change made by the application is silent.
    edited = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._by_application = False
        self.setTabChangesFocus(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(
            f"QPlainTextEdit {{ border-radius: 12px; padding: {_PADDING}px 14px; }}"
        )
        self.document().setDocumentMargin(0)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self.textChanged.connect(self._changed)
        self._fit()

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, text: str) -> None:
        """Replace the text, with the cursor at its end."""
        self._by_application = True
        self.setPlainText(text)
        self._by_application = False
        self.moveCursor(self.textCursor().MoveOperation.End)

    def clear(self) -> None:
        self.setText("")

    def setFont(self, font) -> None:
        super().setFont(font)
        self._fit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in _ENTER:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.insertPlainText("\n")
            else:
                self.submitted.emit()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.escaped.emit()
            return
        super().keyPressEvent(event)

    def _changed(self) -> None:
        if not self._by_application:
            self.edited.emit()

    def _fit(self) -> None:
        # The layout of a plain-text document gives its height in lines.
        lines = max(1, round(self.document().size().height()))
        shown = min(lines, MAX_LINES)
        text_height = shown * self.fontMetrics().lineSpacing()
        self.setFixedHeight(text_height + 2 * (_PADDING + _BORDER))
        scroll = lines > MAX_LINES
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if scroll
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
