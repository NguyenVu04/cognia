"""A drop-down list that shows its arrow.

A styled ``QComboBox`` loses the platform arrow, so this one paints a caret
glyph at its right edge. A click anywhere on the box opens the list.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter, QPaintEvent
from PySide6.QtWidgets import QComboBox, QWidget

from src.ui import icons, theme

CARET_PX = 12
CARET_SPACE = 28


class Dropdown(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(theme.font(13.5))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setFont(icons.icon_font(CARET_PX))
        painter.setPen(theme.TEXT if self.isEnabled() else theme.TEXT_FAINT)
        area = QRect(self.width() - CARET_SPACE, 0, CARET_SPACE - 8, self.height())
        painter.drawText(area, Qt.AlignmentFlag.AlignCenter, icons.glyph("caret-down"))
        painter.end()
