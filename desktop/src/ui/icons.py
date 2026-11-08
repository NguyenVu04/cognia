"""Phosphor icon glyphs.

The codepoints come from ``@phosphor-icons/web@2.1.1`` regular and are fixed
here, so nothing is fetched at run time; the matching ``Phosphor.ttf`` ships in
``src/resources/fonts/``.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QLabel

from src.ui import theme

FAMILY = "Phosphor"

GLYPHS: dict[str, str] = {
    "minus": "\ue32a",
    "x": "\ue4f6",
    "pause": "\ue39e",
    "play": "\ue3d0",
    "chat-circle": "\ue168",
    "brain": "\ue74e",
    "user-focus": "\ue6fc",
    "eye": "\ue220",
    "eye-slash": "\ue224",
    "paper-plane-right": "\ue396",
    "coffee": "\ue1c2",
    "prohibit": "\ue3de",
    "clock": "\ue19a",
    "moon": "\ue330",
    "trash": "\ue4a6",
    "power": "\ue3da",
    "microphone": "\ue326",
    "speaker-high": "\ue44a",
    "speaker-slash": "\ue45a",
    "gear-six": "\ue272",
    "thumbs-up": "\ue48e",
    "thumbs-down": "\ue48c",
    "question": "\ue3e8",
    "arrow-counter-clockwise": "\ue038",
    "magnifying-glass": "\ue30c",
    "plug": "\ue946",
    "sparkle": "\ue6a2",
    "plus": "\ue3d4",
    "check": "\ue182",
    "warning-circle": "\ue4e2",
    "info": "\ue2ce",
    "wind": "\ue5d2",
    "arrows-clockwise": "\ue094",
    "rocket-launch": "\ue3fe",
    "desktop": "\ue560",
    "stop": "\ue46c",
}


def glyph(name: str) -> str:
    """The character for an icon name, such as ``"eye-slash"``."""
    try:
        return GLYPHS[name]
    except KeyError:
        raise KeyError(
            f"icon {name!r} is not in the vendored set; add its codepoint to GLYPHS"
        ) from None


def icon_font(px: float) -> QFont:
    f = QFont(FAMILY)
    f.setPointSizeF(px * theme.PX_TO_PT)
    return f


def icon_label(name: str, px: float, colour: QColor) -> QLabel:
    """An icon as a label that lets clicks through to its parent."""
    label = QLabel(glyph(name))
    label.setFont(icon_font(px))
    label.setStyleSheet(f"color: {theme.css(colour)}; background: transparent;")
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return label


def icon(name: str, px: int, colour: QColor) -> QIcon:
    """The glyph as a QIcon, for buttons and the system tray."""
    ratio = 2
    pixmap = QPixmap(QSize(px * ratio, px * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(icon_font(px * 0.9))
    painter.setPen(colour)
    painter.drawText(0, 0, px, px, Qt.AlignmentFlag.AlignCenter, glyph(name))
    painter.end()
    return QIcon(pixmap)
