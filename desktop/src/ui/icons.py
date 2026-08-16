"""Phosphor icon glyphs.

The design draws its icons from ``@phosphor-icons/web@2.1.1`` regular. The
codepoints below were read out of that package's ``style.css`` and are fixed
here so nothing is fetched at run time; the matching ``Phosphor.ttf`` is
vendored in ``src/resources/fonts/``.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QLabel

FAMILY = "Phosphor"

GLYPHS: dict[str, str] = {
    "minus": "",
    "square": "",
    "x": "",
    "hard-drives": "",
    "pause": "",
    "chat-circle": "",
    "timer": "",
    "brain": "",
    "user-focus": "",
    "eye": "",
    "bell-simple": "",
    "eye-slash": "",
    "paper-plane-right": "",
    "coffee": "",
    "check-circle": "",
    "prohibit": "",
    "pause-circle": "",
    "clock": "",
    "moon": "",
    "power": "",
}


def glyph(name: str) -> str:
    """Return the character for an icon name, e.g. ``"eye-slash"``."""
    try:
        return GLYPHS[name]
    except KeyError:
        raise KeyError(
            f"icon {name!r} is not in the vendored set; add its codepoint to GLYPHS"
        ) from None


def icon_font(px: float) -> QFont:
    f = QFont(FAMILY)
    f.setPointSizeF(px * 72 / 96)
    return f


def icon_label(name: str, px: float, colour: QColor) -> QLabel:
    """An icon as a label, which is how the design uses every one of them."""
    label = QLabel(glyph(name))
    label.setFont(icon_font(px))
    label.setStyleSheet(
        f"color: rgba({colour.red()}, {colour.green()}, "
        f"{colour.blue()}, {colour.alpha()}); background: transparent;"
    )
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return label


def icon(name: str, px: int, colour: QColor) -> QIcon:
    """The same glyph as a QIcon, for the system tray."""
    pixmap = QPixmap(QSize(px, px))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(icon_font(px * 0.82))
    painter.setPen(colour)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyph(name))
    painter.end()
    return QIcon(pixmap)
