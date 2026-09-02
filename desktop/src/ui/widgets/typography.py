"""Label factories for the design's type scale.

Four shapes recur on nearly every screen: the tracked uppercase eyebrow over a
heading, the heading itself, the paragraph under it, and muted body text.
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from src.ui import theme


def _fit(widget: QLabel, text: str, font: QFont, max_width: int) -> None:
    """Size a wrapped label the way CSS ``max-width`` does.

    A wrapping ``QLabel`` picks a roughly square shape from its size hint,
    which is nothing like the browser's shrink-to-fit-then-wrap. Measuring the
    unwrapped run and clamping it reproduces the design's line breaks.
    """
    natural = QFontMetricsF(font).horizontalAdvance(text)
    width = min(int(natural) + 2, max_width)
    widget.setFixedWidth(width)
    # A rich-text label's own height hint under-reports the wrapped height,
    # which lets a layout clip the last line. Ask it directly.
    wrapped = widget.heightForWidth(width)
    if wrapped > 0:
        widget.setMinimumHeight(wrapped)


def label(
    text: str,
    *,
    font: QFont,
    colour: QColor,
    wrap: bool = False,
    max_width: int | None = None,
    parent: QWidget | None = None,
) -> QLabel:
    widget = QLabel(text, parent)
    widget.setFont(font)
    widget.setStyleSheet(f"color: {theme.css(colour)}; background: transparent;")
    widget.setWordWrap(wrap)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    if max_width is not None:
        if wrap:
            _fit(widget, text, font, max_width)
        else:
            widget.setMaximumWidth(max_width)
    return widget


def paragraph(
    text: str,
    *,
    font: QFont,
    colour: QColor,
    line_height: float = 1.6,
    max_width: int | None = None,
    fill: bool = False,
) -> QLabel:
    """Wrapped text at a set line height.

    Qt has no ``line-height`` on a plain label, so the design's 1.5–1.7
    leading comes from a one-element rich-text document instead.

    Two widths are needed and Qt gives neither for free. ``max_width``
    reproduces CSS ``max-width``: shrink to the text, then wrap. ``fill``
    reproduces a block inside a sized container: take the width you are given
    and wrap into it — which needs an ``Ignored`` policy, since a wrapping
    label's own hint is far wider than the box it sits in.
    """
    widget = QLabel()
    widget.setFont(font)
    widget.setTextFormat(Qt.TextFormat.RichText)
    widget.setText(
        f'<div style="line-height: {round(line_height * 100)}%;">'
        f"{escape(text)}</div>"
    )
    widget.setStyleSheet(f"color: {theme.css(colour)}; background: transparent;")
    widget.setWordWrap(True)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    if fill:
        policy = QSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum
        )
        policy.setHeightForWidth(True)
        widget.setSizePolicy(policy)
    elif max_width is not None:
        _fit(widget, text, font, max_width)
    return widget


def eyebrow(text: str, *, alpha: float = 0.4, px: float = 11) -> QLabel:
    """11px, ``.16em`` tracking, uppercase — the small label over a heading."""
    return label(
        text.upper(),
        font=theme.font(px, spacing_em=0.16),
        colour=theme.muted(alpha),
    )


def kicker(text: str, *, alpha: float = 0.38, px: float = 11) -> QLabel:
    """The slightly tighter ``.14em`` variant used inside a screen."""
    return label(
        text.upper(),
        font=theme.font(px, spacing_em=0.14),
        colour=theme.muted(alpha),
    )


def heading(text: str, *, px: float = 25) -> QLabel:
    return label(text, font=theme.font(px, 500, spacing_em=-0.015), colour=theme.TEXT)


def lede(text: str, *, max_width: int = 560, alpha: float = 0.55) -> QLabel:
    """The paragraph under a heading — 15px at 55%, body leading of 1.55."""
    return paragraph(
        text,
        font=theme.font(15),
        colour=theme.muted(alpha),
        line_height=1.55,
        max_width=max_width,
    )


def body(text: str, *, px: float = 13.5, alpha: float = 1.0, weight: int = 400,
         wrap: bool = False, max_width: int | None = None) -> QLabel:
    colour = theme.TEXT if alpha >= 1.0 else theme.muted(alpha)
    return label(
        text,
        font=theme.font(px, weight),
        colour=colour,
        wrap=wrap,
        max_width=max_width,
    )


def set_paragraph_text(
    widget: QLabel,
    text: str,
    *,
    font: QFont,
    line_height: float = 1.6,
    max_width: int | None = None,
) -> None:
    """Replace the text of a :func:`paragraph`, re-fitting it to the new run.

    :func:`paragraph` measures the text once and pins the label to that width.
    A bubble that fills in as the model speaks changes length on every piece,
    so the same measurement has to happen again — otherwise the bubble keeps
    the width of its first two words and grows into a tall thin column.
    """
    widget.setText(
        f'<div style="line-height: {round(line_height * 100)}%;">'
        f"{escape(text)}</div>"
    )
    if max_width is not None:
        _fit(widget, text, font, max_width)
