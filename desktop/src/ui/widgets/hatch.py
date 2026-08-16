"""Striped placeholders standing in for artwork.

The design shows every character sprite and appearance as a hatched box —
``repeating-linear-gradient(135deg, rgba(233,233,237,.055) 0 6px,
transparent 6px 12px)`` with its dimensions written in the middle. No artwork
has been chosen yet (the README records the licence question as open), so the
placeholder is what gets built.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from src.ui import theme

_BAND = 6  # painted band width, px
_PERIOD = 12  # band + gap, px


class HatchPanel(QWidget):
    """A rounded, diagonally hatched box with a centred caption."""

    def __init__(
        self,
        caption: str = "",
        *,
        radius: int = 8,
        alpha: float = 0.055,
        ring: QColor | None = None,
        fill: QColor | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._caption = caption
        self._radius = radius
        self._stripe = QColor(233, 233, 237, round(alpha * 255))
        self._ring = ring
        self._fill = fill
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def setCaption(self, caption: str) -> None:
        self._caption = caption
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(rect, self._radius, self._radius)
        painter.setClipPath(clip)

        # The design gives the sprite box no fill, because in the mockup it sits
        # on a known dark wallpaper. On a real desktop there is nothing behind
        # it and 7%-white hatching disappears, so the free-floating companion
        # supplies its own backdrop.
        if self._fill is not None:
            painter.fillPath(clip, self._fill)

        # 135deg in CSS runs the bands down-right; rotating the painter and
        # drawing upright bands is the same picture and far cheaper to reason
        # about. The span is oversized so the rotation cannot expose a corner.
        painter.save()
        painter.translate(rect.center())
        painter.rotate(-45)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._stripe)
        span = rect.width() + rect.height()
        x = -span
        while x < span:
            painter.drawRect(QRectF(x, -span, _BAND, span * 2))
            x += _PERIOD
        painter.restore()

        if self._ring is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self._ring, 1))
            painter.drawRoundedRect(
                rect.adjusted(0.5, 0.5, -0.5, -0.5), self._radius, self._radius
            )

        if self._caption:
            painter.setPen(theme.muted(0.40))
            painter.setFont(theme.font(9.5, spacing_em=0.08, mono=True))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self._caption,
            )
        painter.end()
