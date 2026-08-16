"""The button shapes the design repeats.

Every button in the mockup is one of a few looks — an accent ring, a plain
``#3f424d`` ring, a dashed ring, or no ring at all — but padding and radius
vary at almost every call site, which no style sheet can parameterise. So one
class takes them as arguments and builds its own sheet from the theme tokens.

Buttons that carry an icon lay out an icon label and a text label themselves,
because Qt gives no control over the gap between a ``QPushButton``'s icon and
its text, and the design sets that gap explicitly everywhere.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from src.ui import icons, theme

Padding = tuple[int, int]  # vertical, horizontal


def _colour_rule(colour: QColor) -> str:
    return f"color: {theme.css(colour)};"


class LayoutButton(QPushButton):
    """A button whose size comes from its child layout.

    ``QPushButton`` measures itself from its own text and icon, so a button
    that lays out real child widgets instead reports a hint far too small and
    collapses. Every button in this file that holds children inherits this.
    """

    def sizeHint(self):  # noqa: N802 - Qt naming
        layout = self.layout()
        return layout.sizeHint() if layout is not None else super().sizeHint()

    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        layout = self.layout()
        return layout.minimumSize() if layout is not None else super().minimumSizeHint()


class TextButton(LayoutButton):
    """A button described by its look rather than by a variant name."""

    def __init__(
        self,
        text: str = "",
        *,
        font: QFont,
        fg: QColor,
        radius: int,
        padding: Padding,
        ring: QColor | None = None,
        fill: QColor | None = None,
        hover_fg: QColor | None = None,
        hover_ring: QColor | None = None,
        hover_fill: QColor | None = None,
        icon_name: str | None = None,
        icon_px: float = 14,
        gap: int = 8,
        align_left: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fg = fg
        self._hover_fg = hover_fg or fg
        self._icon_label: QLabel | None = None
        self._text_label: QLabel | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(font)

        vpad, hpad = padding
        inset = 1 if ring is not None else 0
        border = "border: 0;"
        if ring is not None:
            style = "dashed" if getattr(self, "_dashed", False) else "solid"
            border = f"border: 1px {style} {theme.css(ring)};"

        base = [
            f"border-radius: {radius}px;",
            border,
            f"background: {theme.css(fill) if fill is not None else 'transparent'};",
            _colour_rule(fg),
            "text-align: left;" if align_left else "text-align: center;",
        ]
        if icon_name is None:
            # With an icon the padding lives in the internal layout instead.
            base.append(f"padding: {vpad - inset}px {hpad - inset}px;")
        hover = []
        if hover_fill is not None:
            hover.append(f"background: {theme.css(hover_fill)};")
        if hover_ring is not None:
            hover.append(f"border-color: {theme.css(hover_ring)};")
        if hover_fg is not None:
            hover.append(_colour_rule(hover_fg))

        sheet = "QPushButton {" + " ".join(base) + "}"
        if hover:
            sheet += " QPushButton:hover {" + " ".join(hover) + "}"
        self.setStyleSheet(sheet)

        if icon_name is None:
            self.setText(text)
            # Qt's own hint does not reliably include style-sheet padding, so
            # a long caption gets clipped. Measure it here instead.
            metrics = QFontMetrics(font)
            self.setMinimumWidth(metrics.horizontalAdvance(text) + hpad * 2 + 2)
            self.setMinimumHeight(metrics.height() + vpad * 2)
            return

        # Icon buttons carry their own labels so the gap is exact.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(hpad - inset, vpad - inset, hpad - inset, vpad - inset)
        layout.setSpacing(gap)
        self._icon_label = icons.icon_label(icon_name, icon_px, fg)
        layout.addWidget(self._icon_label)
        if text:
            self._text_label = QLabel(text)
            self._text_label.setFont(font)
            self._text_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
            self._text_label.setStyleSheet(
                _colour_rule(fg) + " background: transparent;"
            )
            layout.addWidget(self._text_label)
        if align_left:
            layout.addStretch(1)
        else:
            layout.insertStretch(0, 1)
            layout.addStretch(1)

    def setLabel(self, text: str) -> None:  # noqa: N802 - matches Qt naming
        """Change the caption, whichever way this button carries one."""
        if self._text_label is not None:
            self._text_label.setText(text)
        else:
            self.setText(text)

    def _paint_labels(self, colour: QColor) -> None:
        for label in (self._icon_label, self._text_label):
            if label is not None:
                label.setStyleSheet(_colour_rule(colour) + " background: transparent;")

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._paint_labels(self._hover_fg)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._paint_labels(self._fg)
        super().leaveEvent(event)


class DashedButton(TextButton):
    """Same shape, dashed ring — the design's two 'try this' affordances."""

    def __init__(self, *args, **kwargs) -> None:
        self._dashed = True
        super().__init__(*args, **kwargs)


# ── the recurring looks, named ─────────────────────────────────────────────


def accent_button(
    text: str,
    *,
    px: float = 14,
    weight: int = 500,
    radius: int = 8,
    padding: Padding = (10, 22),
    icon_name: str | None = None,
    gap: int = 8,
) -> TextButton:
    """Transparent on an accent ring — every primary action in the design."""
    return TextButton(
        text,
        font=theme.font(px, weight),
        fg=theme.ACCENT_TEXT,
        ring=theme.ACCENT,
        radius=radius,
        padding=padding,
        hover_fill=theme.wash(0.12),
        icon_name=icon_name,
        icon_px=px,
        gap=gap,
    )


def quiet_button(
    text: str,
    *,
    px: float = 13.5,
    weight: int = 400,
    radius: int = 8,
    padding: Padding = (11, 16),
    fg: QColor | None = None,
    icon_name: str | None = None,
    gap: int = 8,
) -> TextButton:
    """A plain ``#3f424d`` ring that lifts to the accent on hover."""
    return TextButton(
        text,
        font=theme.font(px, weight),
        fg=fg or theme.muted(0.6),
        ring=theme.BORDER,
        radius=radius,
        padding=padding,
        hover_ring=theme.ACCENT,
        hover_fg=theme.ACCENT_TEXT,
        icon_name=icon_name,
        icon_px=px,
        gap=gap,
    )


def dashed_button(
    text: str,
    *,
    px: float = 13.5,
    radius: int = 8,
    padding: Padding = (10, 16),
    icon_name: str | None = None,
) -> DashedButton:
    return DashedButton(
        text,
        font=theme.font(px),
        fg=theme.muted(0.5),
        ring=theme.BORDER,
        radius=radius,
        padding=padding,
        hover_ring=theme.ACCENT,
        hover_fg=theme.ACCENT_TEXT,
        icon_name=icon_name,
        icon_px=px,
    )


def small_button(text: str, *, radius: int = 6, padding: Padding = (5, 9)) -> TextButton:
    """The 11.5px Edit / Delete / Wrong / Restore controls."""
    return TextButton(
        text,
        font=theme.font(11.5),
        fg=theme.muted(0.6),
        ring=theme.BORDER,
        radius=radius,
        padding=padding,
        hover_ring=theme.ACCENT,
        hover_fg=theme.ACCENT_TEXT,
    )


def menu_button(text: str, icon_name: str, *, px: float = 13.5) -> TextButton:
    """A full-width row in the tray popup."""
    return TextButton(
        text,
        font=theme.font(px),
        fg=theme.muted(0.82),
        radius=7,
        padding=(9, 12),
        hover_fill=theme.wash(0.12),
        hover_fg=theme.ACCENT_TEXT,
        icon_name=icon_name,
        icon_px=px,
        gap=10,
        align_left=True,
    )
