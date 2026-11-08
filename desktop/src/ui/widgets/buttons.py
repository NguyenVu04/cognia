"""The button looks of the interface.

Four variants cover every action: ``primary`` for the one main action of a
place, ``secondary`` for the others, ``ghost`` for quiet ones in a row, and
``danger`` for what cannot be undone. Two sizes: ``normal`` and ``small``.
Hover and pressed looks live in the button's own style sheet, so nothing is
restyled while the pointer moves.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton, QWidget

from src.ui import icons, theme

# vertical padding, horizontal padding, pixel size, radius, icon size
_SIZES = {
    "normal": (9, 16, 13.5, 10, 16),
    "small": (5, 10, 12, 8, 13),
}


def _look(variant: str) -> tuple[QColor, QColor | None, QColor | None, QColor]:
    """Text colour, fill, ring and hover fill of a variant."""
    match variant:
        case "primary":
            return theme.ON_ACCENT, theme.ACCENT, None, theme.ACCENT_TEXT
        case "secondary":
            return theme.TEXT, None, theme.BORDER, theme.wash(0.14)
        case "ghost":
            return theme.TEXT_SECONDARY, None, None, theme.wash(0.12)
        case "danger":
            return theme.DANGER, None, theme.DANGER, theme.wash(0.10)
    raise ValueError(f"no button variant {variant!r}")


class LayoutButton(QPushButton):
    """A button whose size comes from the child layout it holds."""

    def sizeHint(self):
        layout = self.layout()
        return layout.sizeHint() if layout is not None else super().sizeHint()

    def minimumSizeHint(self):
        layout = self.layout()
        return layout.minimumSize() if layout is not None else super().minimumSizeHint()


class Button(QPushButton):
    """A text button, optionally with an icon before the text."""

    def __init__(
        self,
        text: str = "",
        *,
        variant: str = "secondary",
        size: str = "normal",
        icon_name: str | None = None,
        tooltip: str = "",
        align_left: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        vpad, hpad, px, radius, icon_px = _SIZES[size]
        fg, fill, ring, hover = _look(variant)
        self.setFont(theme.font(px, 700 if variant == "primary" else 600))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        if icon_name is not None:
            self.setIcon(icons.icon(icon_name, icon_px, fg))
            self.setIconSize(QSize(icon_px, icon_px))
        inset = 1 if ring is not None else 0
        border = f"1px solid {theme.css(ring)}" if ring is not None else "0"
        pressed = theme.wash(0.22) if variant != "primary" else theme.ACCENT_2
        self.setStyleSheet(
            "QPushButton {"
            f"color: {theme.css(fg)};"
            f"background: {theme.css(fill) if fill is not None else 'transparent'};"
            f"border: {border}; border-radius: {radius}px;"
            f"padding: {vpad - inset}px {hpad - inset}px;"
            f"text-align: {'left' if align_left else 'center'};"
            "}"
            f"QPushButton:hover {{ background: {theme.css(hover)}; }}"
            f"QPushButton:pressed {{ background: {theme.css(pressed)}; }}"
            "QPushButton:disabled {"
            f"color: {theme.css(theme.TEXT_FAINT)};"
            f"background: {theme.css(theme.BG_INSET)};"
            f"border-color: {theme.css(theme.BORDER_SUBTLE)};"
            "}"
            f"QPushButton:focus {{ outline: none; border: 1px solid "
            f"{theme.css(theme.ACCENT_2)}; }}"
        )

    def setLabel(self, text: str) -> None:
        self.setText(text)


class IconButton(QPushButton):
    """A round button that holds one icon and says what it does in a tooltip."""

    def __init__(
        self,
        icon_name: str,
        tooltip: str,
        *,
        px: int = 18,
        box: int = 36,
        colour: QColor = theme.TEXT_SECONDARY,
        checkable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._px = px
        self.setIcon(icons.icon(icon_name, px, colour))
        self.setIconSize(QSize(px, px))
        self.setFixedSize(box, box)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton {"
            f"border: 0; border-radius: {box // 2}px; background: transparent;"
            "}"
            f"QPushButton:hover {{ background: {theme.css(theme.wash(0.14))}; }}"
            f"QPushButton:checked {{ background: {theme.css(theme.wash(0.26))}; }}"
            f"QPushButton:pressed {{ background: {theme.css(theme.wash(0.30))}; }}"
            f"QPushButton:focus {{ outline: none; border: 1px solid "
            f"{theme.css(theme.ACCENT_2)}; }}"
        )

    def setGlyph(self, icon_name: str, colour: QColor = theme.TEXT_SECONDARY) -> None:
        self.setIcon(icons.icon(icon_name, self._px, colour))
