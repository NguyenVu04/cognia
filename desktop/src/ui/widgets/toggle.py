"""The pill switch used by desk awareness and the message-kind rows.

Two sizes appear in the design, 52×29 and 46×26, both animating the knob left
to right over ``.18s ease``.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QWidget

from src.ui import theme

_SIZES = {
    # width, height, radius, knob diameter, knob inset
    "large": (52, 29, 15, 21, 3),
    "small": (46, 26, 14, 18, 3),
}


class PillToggle(QAbstractButton):
    """A checkable switch. Presentational — nothing is stored."""

    def __init__(
        self, size: str = "large", checked: bool = True, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._w, self._h, self._radius, self._knob, self._inset = _SIZES[size]
        self.setCheckable(True)
        self.setFixedSize(self._w, self._h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._pos = float(self._travel() if checked else self._inset)
        self._animation = QPropertyAnimation(self, b"knobPos", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.setChecked(checked)
        self.toggled.connect(self._animate)

    def _travel(self) -> int:
        return self._w - self._knob - self._inset

    def _animate(self, on: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._pos)
        self._animation.setEndValue(float(self._travel() if on else self._inset))
        self._animation.start()

    def getKnobPos(self) -> float:  # noqa: N802 - Qt property accessor
        return self._pos

    def setKnobPos(self, value: float) -> None:  # noqa: N802 - Qt property accessor
        self._pos = value
        self.update()

    knobPos = Property(float, getKnobPos, setKnobPos)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        on = self.isChecked()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = theme.wash(0.12) if on else Qt.GlobalColor.transparent
        ring = theme.ACCENT if on else theme.BORDER
        painter.setBrush(track)
        painter.setPen(QPen(ring, 1))
        painter.drawRoundedRect(
            self.rect().adjusted(0, 0, -1, -1), self._radius, self._radius
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.ACCENT_TEXT if on else theme.KNOB_OFF)
        painter.drawEllipse(
            int(self._pos), self._inset, self._knob, self._knob
        )
        painter.end()
