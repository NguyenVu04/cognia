"""The 42px window bar.

The window is frameless, so the bar draws its own controls and carries the
drag that moves the window.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from src.ui import icons, theme
from src.ui.widgets.surface import StyledWidget
from src.ui.widgets.typography import label

HEIGHT = 42
_BUTTONS = ("minus", "square", "x")


class _Dot(StyledWidget):
    """The 7px accent dot beside the wordmark."""

    def __init__(self, colour: QColor, size: int = 7) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self.setRules(
            f"background: {theme.css(colour)}; border-radius: {size / 2}px;"
        )


class _WindowButton(QLabel):
    """A 30×24 hit target holding one Phosphor glyph."""

    clicked = Signal()

    def __init__(self, name: str) -> None:
        super().__init__(icons.glyph(name))
        self.setFixedSize(30, 24)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(icons.icon_font(14))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paint(theme.muted(0.45), None)

    def _paint(self, fg: QColor, bg: QColor | None) -> None:
        fill = theme.css(bg) if bg is not None else "transparent"
        self.setStyleSheet(
            f"color: {theme.css(fg)}; background: {fill}; border-radius: 5px;"
        )

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._paint(theme.TEXT, theme.wash(0.12))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._paint(theme.muted(0.45), None)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class TitleBar(StyledWidget):
    """Wordmark on the left, window controls on the right."""

    minimiseRequested = Signal()
    closeRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(HEIGHT)
        self.setRules(
            f"background: {theme.css(theme.BG_TITLEBAR)};"
            f"border-bottom: 1px solid {theme.css(theme.BORDER_SUBTLE)};"
        )
        self._drag_offset: QPoint | None = None

        row = QHBoxLayout(self)
        row.setContentsMargins(18, 0, 14, 0)
        row.setSpacing(0)

        left = QHBoxLayout()
        left.setSpacing(10)
        left.addWidget(_Dot(theme.ACCENT))
        left.addWidget(label("Cognia", font=theme.font(12.5), colour=theme.muted(0.6)))
        row.addLayout(left)
        row.addStretch(1)

        right = QHBoxLayout()
        right.setSpacing(4)
        for name in _BUTTONS:
            button = _WindowButton(name)
            if name == "minus":
                button.clicked.connect(self.minimiseRequested)
            elif name == "x":
                button.clicked.connect(self.closeRequested)
            right.addWidget(button)
        row.addLayout(right)

    # Dragging the frameless window by its bar.

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            self._drag_offset = (
                event.globalPosition().toPoint() - window.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._drag_offset is not None:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._drag_offset = None
        super().mouseReleaseEvent(event)
