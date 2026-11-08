"""The window bar. The window is frameless, so the bar draws its own controls
and carries the drag that moves the window."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from src.ui import theme
from src.ui.widgets.buttons import IconButton
from src.ui.widgets.surface import StyledWidget
from src.ui.widgets.typography import label

HEIGHT = 40


class TitleBar(StyledWidget):
    """The name on the left, minimise and close on the right."""

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
        row.setContentsMargins(16, 0, 8, 0)
        row.setSpacing(4)
        dot = StyledWidget()
        dot.setFixedSize(8, 8)
        dot.setRules(f"background: {theme.css(theme.ACCENT)}; border-radius: 4px;")
        row.addWidget(dot)
        row.addSpacing(6)
        row.addWidget(label("Cognia", font=theme.font(13, 700)))
        row.addStretch(1)

        self.minimise = IconButton("minus", "Minimise", px=15, box=30)
        self.minimise.clicked.connect(self.minimiseRequested)
        row.addWidget(self.minimise)
        self.close_button = IconButton(
            "x", "Close — Cognia keeps running", px=15, box=30
        )
        self.close_button.clicked.connect(self.closeRequested)
        row.addWidget(self.close_button)
        for button in (self.minimise, self.close_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            self._drag_offset = (
                event.globalPosition().toPoint() - window.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)
