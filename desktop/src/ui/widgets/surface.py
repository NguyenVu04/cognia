"""Filled, ringed, rounded panels — the card shapes the design repeats.

Two Qt behaviours shape this module:

* A style sheet set on a widget applies to that widget **and all its
  descendants**. An unscoped ``border-bottom`` on a row therefore draws a line
  under every label inside it too. Everything here scopes its rules to its own
  object name, which is unique per instance.
* Qt ignores ``background`` and ``border`` on a bare ``QWidget`` unless
  ``WA_StyledBackground`` is set.

The design draws every card as ``box-shadow: 0 0 0 1px <ring>``, a ring that
sits outside the box and costs no space. Qt has no such thing, so the ring
becomes a 1px border and :class:`Panel` takes one pixel back off each padding
edge to keep the interior the size the design specifies.
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
    """Mixin giving a widget style rules that cannot leak to its children."""

    def _init_scope(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName(f"{type(self).__name__}{next(_ids)}")
        self._rules: list[str] = []

    def setRules(self, rules: str) -> None:  # noqa: N802 - matches Qt naming
        self._rules = [rules]
        self._applyRules()

    def addRules(self, rules: str) -> None:  # noqa: N802 - matches Qt naming
        """Add rules without disturbing what is already set."""
        self._rules.append(rules)
        self._applyRules()

    def _applyRules(self) -> None:  # noqa: N802 - matches Qt naming
        self.setStyleSheet(f"#{self.objectName()} {{ {' '.join(self._rules)} }}")


class StyledWidget(_Scoped, QWidget):
    """A plain widget that paints its own style sheet and nothing else's."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_scope()


def bottom_rule(parent: QWidget | None = None) -> StyledWidget:
    """A row carrying the design's ``border-bottom`` hairline."""
    widget = StyledWidget(parent)
    widget.setRules(f"border-bottom: 1px solid {theme.css(theme.HAIRLINE)};")
    return widget


class Panel(_Scoped, QFrame):
    """A rounded surface, optionally ringed."""

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
        ]
        inset = 0
        if ring is not None:
            rules.append(f"border: 1px solid {theme.css(ring)};")
            inset = 1
        else:
            rules.append("border: 0;")
        self.setRules(" ".join(rules))

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


def rule(colour: QColor, thickness: int = 1) -> StyledWidget:
    """A horizontal hairline, as the design's divider inside a card."""
    line = StyledWidget()
    line.setFixedHeight(thickness)
    line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    line.setRules(f"background: {theme.css(colour)}; border: 0;")
    return line


def fading_rule(colour: QColor, thickness: int = 1) -> StyledWidget:
    """The divider inside the session card, which fades out at 70%."""
    line = StyledWidget()
    line.setFixedHeight(thickness)
    line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    solid = theme.css(colour)
    clear = theme.css(QColor(colour.red(), colour.green(), colour.blue(), 0))
    line.setRules(
        "border: 0; background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f" stop:0 {solid}, stop:0.7 {solid}, stop:1 {clear});"
    )
    return line


def vrule(colour: QColor, thickness: int = 1) -> StyledWidget:
    """A vertical hairline."""
    line = StyledWidget()
    line.setFixedWidth(thickness)
    line.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
    line.setRules(f"background: {theme.css(colour)}; border: 0;")
    return line
