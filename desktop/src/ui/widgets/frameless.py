"""Frameless top-level windows.

The window draws no shadow of its own. ``app/`` gives each window marked with
the ``nativeFrame`` property the shadow and rounded corners of Windows, which
cost nothing when the window repaints.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget

from src.ui import theme
from src.ui.widgets.surface import Panel

NATIVE_FRAME = "nativeFrame"


class FramelessWindow(QWidget):
    """A frameless top level whose visible surface is :attr:`body`."""

    def __init__(
        self,
        *,
        fill: QColor = theme.BG_WINDOW,
        flags: Qt.WindowType = Qt.WindowType.Window,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, flags | Qt.WindowType.FramelessWindowHint)
        self.setProperty(NATIVE_FRAME, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.body = Panel(fill=fill, ring=theme.BORDER)
        outer.addWidget(self.body)

    def resize_body(self, width: int, height: int) -> None:
        self.setFixedSize(width, height)
