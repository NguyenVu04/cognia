"""A turning arc that says the application is still working.

It turns only while it is shown, so a hidden spinner costs nothing.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget

from src.ui import theme

SIZE = 28
_ARC_DEGREES = 100
_STEP_DEGREES = 12
# About 30 turns a second: smooth enough, and cheap while it runs.
_TICK_MS = 33
_PEN = 3


class Spinner(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(SIZE, SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._turn)

    @property
    def turning(self) -> bool:
        return self._timer.isActive()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def _turn(self) -> None:
        self._angle = (self._angle + _STEP_DEGREES) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(_PEN, _PEN, -_PEN, -_PEN)
        track = QPen(theme.wash(0.22), _PEN)
        painter.setPen(track)
        painter.drawEllipse(box)
        arc = QPen(theme.ACCENT, _PEN)
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc)
        # Qt measures arcs in sixteenths of a degree, counter-clockwise from 3 o'clock.
        painter.drawArc(box, (90 - self._angle) * 16, -_ARC_DEGREES * 16)
