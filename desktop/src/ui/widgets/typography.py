"""Label factories for the type scale.

Headings, the paragraph under a heading, body text and small captions recur on
every screen, each in one of the text colours of :mod:`src.ui.theme`.
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from src.ui import theme


def _fit(widget: QLabel, text: str, font: QFont, max_width: int) -> None:
    """Shrink a wrapped label to its text, then wrap at ``max_width``.

    A wrapping ``QLabel`` otherwise picks a near-square shape.
    """
    natural = QFontMetricsF(font).horizontalAdvance(text)
    width = min(int(natural) + 2, max_width)
    widget.setFixedWidth(width)
    # A rich-text label under-reports its wrapped height, which clips the
    # last line.
    wrapped = widget.heightForWidth(width)
    if wrapped > 0:
        widget.setMinimumHeight(wrapped)


def _colour(widget: QLabel, colour: QColor) -> None:
    widget.setStyleSheet(f"color: {theme.css(colour)}; background: transparent;")


def label(
    text: str,
    *,
    font: QFont,
    colour: QColor = theme.TEXT,
    wrap: bool = False,
    max_width: int | None = None,
    parent: QWidget | None = None,
) -> QLabel:
    widget = QLabel(text, parent)
    widget.setFont(font)
    _colour(widget, colour)
    widget.setWordWrap(wrap)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    if max_width is not None:
        if wrap:
            _fit(widget, text, font, max_width)
        else:
            widget.setMaximumWidth(max_width)
    return widget


def _rich(text: str, line_height: float) -> str:
    return (
        f'<div style="line-height: {round(line_height * 100)}%;">'
        f"{escape(text)}</div>"
    )


def paragraph(
    text: str,
    *,
    font: QFont,
    colour: QColor = theme.TEXT,
    line_height: float = 1.55,
    max_width: int | None = None,
    fill: bool = False,
    selectable: bool = False,
) -> QLabel:
    """Wrapped text at a set line height.

    ``max_width`` shrinks the label to its text and wraps there. ``fill`` takes
    the width the layout gives and wraps into it.
    """
    widget = QLabel()
    widget.setFont(font)
    widget.setTextFormat(Qt.TextFormat.RichText)
    widget.setText(_rich(text, line_height))
    _colour(widget, colour)
    widget.setWordWrap(True)
    widget.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        if selectable
        else Qt.TextInteractionFlag.NoTextInteraction
    )
    if fill:
        policy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        widget.setSizePolicy(policy)
    elif max_width is not None:
        _fit(widget, text, font, max_width)
    return widget


def set_paragraph_text(
    widget: QLabel,
    text: str,
    *,
    font: QFont,
    line_height: float = 1.55,
    max_width: int | None = None,
) -> None:
    """Replace the text of a :func:`paragraph` and fit it again."""
    widget.setText(_rich(text, line_height))
    if max_width is not None:
        _fit(widget, text, font, max_width)


def heading(text: str, *, px: float = 24) -> QLabel:
    return label(text, font=theme.font(px, 700))


def subheading(text: str, *, px: float = 15) -> QLabel:
    return label(text, font=theme.font(px, 700))


def kicker(text: str) -> QLabel:
    """The small uppercase label over a group."""
    return label(text.upper(), font=theme.font(11.5, 800), colour=theme.TEXT_FAINT)


def lede(text: str, *, max_width: int = 600) -> QLabel:
    """The paragraph under a heading."""
    return paragraph(
        text, font=theme.font(14.5), colour=theme.TEXT_SECONDARY, max_width=max_width
    )


def body(
    text: str,
    *,
    px: float = 13.5,
    colour: QColor = theme.TEXT,
    weight: int = 400,
    wrap: bool = False,
    max_width: int | None = None,
) -> QLabel:
    return label(
        text, font=theme.font(px, weight), colour=colour, wrap=wrap,
        max_width=max_width,
    )


def caption(text: str, *, px: float = 12) -> QLabel:
    return label(text, font=theme.font(px), colour=theme.TEXT_FAINT)
