"""The companion on the desktop — UC-20.

A frameless, always-on-top window holding the sprite and, above it, the break
nudge. It can be dragged anywhere, hidden, and brought back, and it is never
the only route to anything.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLayout, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.widgets.hatch import HatchPanel
from src.ui.widgets.nudge_bubble import NudgeBubble
from src.ui.widgets.shadow import apply_shadow

SPRITE_WIDTH = 172
SPRITE_HEIGHT = 214
MARGIN = 44  # transparent gutter the nudge shadow is painted into


class CompanionWindow(QWidget):
    """Sprite plus nudge. Presentational — it observes nothing."""

    moved = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,  # keeps it off the taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_offset: QPoint | None = None
        self.margin = MARGIN

        column = QVBoxLayout(self)
        column.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        column.setSpacing(12)
        # The window is exactly its content: hiding the nudge shrinks it.
        column.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        # The bubble is right-aligned with the sprite and overhangs to the left.
        bubble_row = QHBoxLayout()
        bubble_row.setContentsMargins(0, 0, 0, 0)
        bubble_row.addStretch(1)
        self.nudge = NudgeBubble()
        apply_shadow(self.nudge, blur=40, dy=18, colour=theme.SHADOW)
        self.nudge.dismissed.connect(self.hideNudge)
        bubble_row.addWidget(self.nudge)
        column.addLayout(bubble_row)

        sprite_row = QHBoxLayout()
        sprite_row.setContentsMargins(0, 0, 0, 0)
        sprite_row.addStretch(1)
        self.sprite = HatchPanel(
            "anime-style sprite\ndrag me\n172×214",
            radius=10, alpha=0.07, ring=theme.muted(0.09),
            fill=QColor(theme.BG_WINDOW.red(), theme.BG_WINDOW.green(),
                        theme.BG_WINDOW.blue(), 219),
        )
        self.sprite.setFixedSize(SPRITE_WIDTH, SPRITE_HEIGHT)
        sprite_row.addWidget(self.sprite)
        column.addLayout(sprite_row)

        self.adjustSize()

    # ── nudge ─────────────────────────────────────────────────────────────

    def showNudge(self) -> None:  # noqa: N802 - matches Qt naming
        self.nudge.reset()
        self.nudge.setVisible(True)
        self.adjustSize()

    def hideNudge(self) -> None:  # noqa: N802 - matches Qt naming
        self.nudge.setVisible(False)
        self.adjustSize()

    # ── dragging ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self.moved.emit()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._drag_offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)
