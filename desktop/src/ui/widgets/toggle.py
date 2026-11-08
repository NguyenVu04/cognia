"""The pill switch for every on/off setting, in two sizes."""

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
    """A checkable switch. It stores nothing; its owner reports the change."""

    def __init__(
        self, size: str = "large", checked: bool = True, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._w, self._h, self._radius, self._knob, self._inset = _SIZES[size]
        self.setCheckable(True)
        self.setFixedSize(self._w, self._h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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

    def getKnobPos(self) -> float:
        return self._pos

    def setKnobPos(self, value: float) -> None:
        self._pos = value
        self.update()

    knobPos = Property(float, getKnobPos, setKnobPos)

    def paintEvent(self, event) -> None:
        on = self.isChecked()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = theme.ACCENT if on else theme.BG_INSET
        ring = theme.ACCENT_2 if self.hasFocus() else (
            theme.ACCENT if on else theme.BORDER
        )
        painter.setBrush(track)
        painter.setPen(QPen(ring, 1))
        painter.drawRoundedRect(
            self.rect().adjusted(0, 0, -1, -1), self._radius, self._radius
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.BG_WINDOW if on else theme.KNOB_OFF)
        painter.drawEllipse(
            int(self._pos), self._inset, self._knob, self._knob
        )
        painter.end()
