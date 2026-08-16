"""Frameless windows that carry the design's drop shadows.

Three surfaces in the design float above everything else with a real shadow:
the main window (``0 24px 70px``), the break-nudge bubble (``0 18px 40px``)
and the tray popup (``0 20px 48px``). Qt cannot paint a shadow outside a
window, so each is a translucent frameless top level with a transparent margin
and a :class:`~src.ui.widgets.surface.Panel` inside carrying the effect.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.widgets.surface import Panel


def apply_shadow(
    widget: QWidget, *, blur: int, dy: int, colour: QColor = theme.SHADOW
) -> QGraphicsDropShadowEffect:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setXOffset(0)
    effect.setYOffset(dy)
    effect.setColor(colour)
    widget.setGraphicsEffect(effect)
    return effect


class ShadowWindow(QWidget):
    """A frameless top level whose visible surface is :attr:`body`.

    ``margin`` is the transparent gutter the shadow is painted into; it is
    part of the window but draws nothing.
    """

    def __init__(
        self,
        *,
        radius: int,
        fill: QColor,
        ring: QColor | None = None,
        blur: int,
        dy: int,
        shadow_colour: QColor = theme.SHADOW,
        margin: int = 48,
        flags: Qt.WindowType = Qt.WindowType.Window,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, flags | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.margin = margin

        outer = QVBoxLayout(self)
        outer.setContentsMargins(margin, margin, margin, margin)
        outer.setSpacing(0)

        self.body = Panel(fill=fill, ring=ring, radius=radius)
        outer.addWidget(self.body)
        apply_shadow(self.body, blur=blur, dy=dy, colour=shadow_colour)

    def resize_body(self, width: int, height: int) -> None:
        """Size the window so that its visible surface is exactly w×h."""
        self.setFixedSize(width + self.margin * 2, height + self.margin * 2)
