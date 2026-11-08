"""Filled, ringed, rounded panels.

A style sheet set on a widget also applies to all its descendants, so every
widget here scopes its rules to its own unique object name. Qt also ignores
``background`` and ``border`` on a bare ``QWidget`` unless
``WA_StyledBackground`` is set, which these widgets do.
"""

from __future__ import annotations

from itertools import count

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QSizePolicy, QVBoxLayout, QWidget

from src.ui import theme

Padding = tuple[int, int, int, int]  # top, right, bottom, left

_ids = count()


class _Scoped:
    """Gives a widget style rules that cannot leak to its children."""

    def _init_scope(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName(f"{type(self).__name__}{next(_ids)}")
        self._rules: list[str] = []

    def setRules(self, rules: str) -> None:
        self._rules = [rules]
        self._apply_rules()

    def addRules(self, rules: str) -> None:
        """Add rules and keep those already set."""
        self._rules.append(rules)
        self._apply_rules()

    def _apply_rules(self) -> None:
        self.setStyleSheet(f"#{self.objectName()} {{ {' '.join(self._rules)} }}")


class StyledWidget(_Scoped, QWidget):
    """A plain widget that paints its own style sheet and nothing else's."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_scope()


def bottom_rule(parent: QWidget | None = None) -> StyledWidget:
    """A row with a hairline under it."""
    widget = StyledWidget(parent)
    widget.setRules(f"border-bottom: 1px solid {theme.css(theme.HAIRLINE)};")
    return widget


class Panel(_Scoped, QFrame):
    """A rounded surface, optionally ringed. A ring takes one pixel off each
    padding edge, so the inside keeps the size asked for."""

    def __init__(
        self,
        *,
        fill: QColor | None = None,
        ring: QColor | None = None,
        radius: int = 0,
        padding: Padding = (0, 0, 0, 0),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._init_scope()
        rules = [
            f"border-radius: {radius}px;",
            f"background: {theme.css(fill)};" if fill is not None
            else "background: transparent;",
            f"border: 1px solid {theme.css(ring)};" if ring is not None
            else "border: 0;",
        ]
        self.setRules(" ".join(rules))
        inset = 1 if ring is not None else 0
        top, right, bottom, left = padding
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            max(left - inset, 0),
            max(top - inset, 0),
            max(right - inset, 0),
            max(bottom - inset, 0),
        )
        layout.setSpacing(0)

    def body(self) -> QVBoxLayout:
        """The panel's own layout, to add content to."""
        return self.layout()


def card(padding: Padding = (16, 18, 16, 18), radius: int = 12) -> Panel:
    """The standard card: card fill on a subtle ring."""
    return Panel(
        fill=theme.BG_CARD, ring=theme.BORDER_SUBTLE, radius=radius, padding=padding
    )


def rule(colour: QColor = theme.HAIRLINE, thickness: int = 1) -> StyledWidget:
    """A horizontal hairline."""
    line = StyledWidget()
    line.setFixedHeight(thickness)
    line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    line.setRules(f"background: {theme.css(colour)}; border: 0;")
    return line
