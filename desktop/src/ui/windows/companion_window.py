"""The companion on the desktop.

A frameless, always-on-top window holding the sprite and, above it, the break
nudge. It can be dragged anywhere, hidden, and brought back, and it is never
the only route to anything.

Until the 3D character exists, the sprite is a placeholder that writes what the
character would show: its face, a gesture, and an exercise done together. The
methods keep the names the 3D page will have, so only their bodies change.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QElapsedTimer, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLayout, QVBoxLayout, QWidget

from src.domain.tools.models import ActivityStep
from src.ui import theme
from src.ui.widgets.hatch import HatchPanel
from src.ui.widgets.nudge_bubble import NudgeBubble
from src.ui.widgets.shadow import apply_shadow

SPRITE_WIDTH = 172
SPRITE_HEIGHT = 214
MARGIN = 44  # transparent gutter the nudge shadow is painted into
# A gesture is a short clip, about as long as this.
GESTURE_MS = 2000
_PLACEHOLDER = "anime-style sprite\ndrag me\n172×214"


class CompanionWindow(QWidget):
    """Sprite plus nudge. Presentational — it observes nothing."""

    moved = Signal()
    #: An exercise stopped: its name and how many seconds it ran.
    activityEnded = Signal(str, int)

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
        self._expression = ""
        self._gesture = ""
        self._gesture_timer = QTimer(self)
        self._gesture_timer.setSingleShot(True)
        self._gesture_timer.setInterval(GESTURE_MS)
        self._gesture_timer.timeout.connect(self._end_gesture)
        self._activity = ""
        self._steps: tuple[ActivityStep, ...] = ()
        self._step = 0
        self._left = 0
        self._ran = QElapsedTimer()
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._count_down)
        self.sprite = HatchPanel(
            _PLACEHOLDER,
            radius=10, alpha=0.07, ring=theme.muted(0.09),
            fill=QColor(theme.BG_WINDOW.red(), theme.BG_WINDOW.green(),
                        theme.BG_WINDOW.blue(), 219),
        )
        self.sprite.setFixedSize(SPRITE_WIDTH, SPRITE_HEIGHT)
        sprite_row.addWidget(self.sprite)
        column.addLayout(sprite_row)

        self.adjustSize()

    # ── what the character shows ──────────────────────────────────────────

    def setExpression(self, preset: str, weight: float) -> None:  # noqa: N802
        """Show the face ``preset`` at ``weight``, from 0 to 1."""
        self._expression = f"{preset} · {weight:.2f}"
        self._refresh()

    def playGesture(self, name: str) -> None:  # noqa: N802 - matches Qt naming
        """Play ``name`` once. A new gesture replaces the one playing."""
        self._gesture = name
        self._gesture_timer.start()
        self._refresh()

    def playActivity(  # noqa: N802 - matches Qt naming
        self, name: str, steps: Sequence[ActivityStep]
    ) -> None:
        """Do the exercise ``name`` step by step. It ends when the steps run
        out, or on :meth:`stopActivity`."""
        if not steps:
            return
        self._activity, self._steps, self._step = name, tuple(steps), 0
        self._left = self._steps[0].seconds
        self._ran.start()
        self._tick.start()
        self._refresh()

    def stopActivity(self) -> None:  # noqa: N802 - matches Qt naming
        """End the exercise now, and say how long it ran."""
        if not self._activity:
            return
        name, seconds = self._activity, int(self._ran.elapsed() // 1000)
        self._tick.stop()
        self._activity, self._steps = "", ()
        self._refresh()
        self.activityEnded.emit(name, seconds)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.stopActivity()
        super().mouseDoubleClickEvent(event)

    def _count_down(self) -> None:
        self._left -= 1
        if self._left <= 0:
            self._step += 1
            if self._step >= len(self._steps):
                self.stopActivity()
                return
            self._left = self._steps[self._step].seconds
        self._refresh()

    def caption(self) -> str:
        """What the placeholder shows now."""
        lines = [line for line in self._state_lines() if line]
        return "\n".join([*lines, "drag me"]) if lines else _PLACEHOLDER

    def _state_lines(self) -> list[str]:
        doing = ""
        if self._activity:
            step = self._steps[self._step].label
            doing = f"{self._activity} · {step} · {self._left}"
        return [self._expression, self._gesture, doing]

    def _end_gesture(self) -> None:
        self._gesture = ""
        self._refresh()

    def _refresh(self) -> None:
        self.sprite.setCaption(self.caption())

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
