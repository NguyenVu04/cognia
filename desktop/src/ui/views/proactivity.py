"""Speaking up — UC-18.

Everything the companion does uninvited, on one page. Movement counts as
speech (BR-07), so it is governed here too.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.views import sample_data
from src.ui.widgets.buttons import LayoutButton
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import Panel, bottom_rule
from src.ui.widgets.toggle import PillToggle
from src.ui.widgets.typography import body, eyebrow, heading, kicker, label, lede

COLUMN_WIDTH = 660


class LevelCard(LayoutButton):
    """One of Quiet / Moderate / Present, selected by its ring and fill."""

    def __init__(self, level: sample_data.Level, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.level = level
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)

        column = QVBoxLayout(self)
        column.setContentsMargins(16, 14, 16, 14)
        column.setSpacing(2)
        self._name = label(level.name, font=theme.font(14.5, 500), colour=theme.TEXT)
        self._detail = label(
            level.detail, font=theme.font(12), colour=theme.muted(0.5)
        )
        for child in (self._name, self._detail):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        column.addWidget(self._name)
        column.addWidget(self._detail)

        self.setActive(False)

    def setActive(self, active: bool) -> None:  # noqa: N802 - matches Qt naming
        self.setChecked(active)
        fill = theme.wash(0.09) if active else theme.BG_CARD
        ring = theme.ACCENT if active else theme.BORDER_SUBTLE
        fg = theme.ACCENT_TEXT if active else theme.TEXT
        self.setStyleSheet(
            "QPushButton {"
            f"border-radius: 9px; border: 1px solid {theme.css(ring)};"
            f"background: {theme.css(fill)};"
            "}"
        )
        self._name.setStyleSheet(
            f"color: {theme.css(fg)}; background: transparent;"
        )


class ProactivityView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        pane = ScrollPane(padding=(34, 40, 40, 40))
        layout.addWidget(pane)
        column = pane.column

        column.addWidget(eyebrow("UC-18"))
        column.addSpacing(6)
        column.addWidget(heading("How much it speaks up"))
        column.addSpacing(4)
        column.addWidget(
            lede(
                "Everything the companion does uninvited, on one page. "
                "Movement counts as speech (BR-07).",
                max_width=600,
            )
        )
        column.addSpacing(28)
        column.addWidget(self._panel(), 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)

    def _panel(self) -> QWidget:
        holder = QWidget()
        holder.setFixedWidth(COLUMN_WIDTH)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        column.addWidget(body("How often it may speak", px=13, weight=500))
        column.addSpacing(10)

        levels = QHBoxLayout()
        levels.setSpacing(8)
        self._levels: list[LevelCard] = []
        for level in sample_data.LEVELS:
            card = LevelCard(level)
            card.clicked.connect(lambda _=False, c=card: self._select(c))
            levels.addWidget(card, 1)
            self._levels.append(card)
        column.addLayout(levels)
        self._select(self._levels[1])  # "Moderate" is the specified default

        column.addSpacing(26)
        column.addWidget(self._quiet_hours())

        column.addSpacing(26)
        column.addWidget(kicker("Kinds of message"))
        column.addSpacing(10)
        for kind in sample_data.KINDS:
            column.addWidget(self._kind_row(kind))
        return holder

    def _select(self, chosen: LevelCard) -> None:
        for card in self._levels:
            card.setActive(card is chosen)

    def _quiet_hours(self) -> Panel:
        card = Panel(
            fill=theme.BG_CARD, ring=theme.BORDER_SUBTLE, radius=9,
            padding=(16, 18, 16, 18),
        )
        row = QHBoxLayout()
        row.setSpacing(20)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(body("Quiet hours", px=14))
        text.addWidget(
            body("Also while the machine is locked, or you are presenting",
                 px=12.5, alpha=0.5)
        )
        row.addLayout(text, 1)
        row.addWidget(
            label(sample_data.QUIET_HOURS,
                  font=theme.font(15, tabular=True), colour=theme.ACCENT_TEXT),
            0, Qt.AlignmentFlag.AlignVCenter,
        )
        card.body().addLayout(row)
        return card

    def _kind_row(self, kind: sample_data.MessageKind) -> QWidget:
        widget = bottom_rule()
        row = QHBoxLayout(widget)
        row.setContentsMargins(2, 13, 2, 13)
        row.setSpacing(20)

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(body(kind.name, px=14))
        text.addWidget(body(kind.detail, px=12, alpha=0.45))
        row.addLayout(text, 1)
        row.addWidget(
            PillToggle("small", checked=True), 0, Qt.AlignmentFlag.AlignVCenter
        )
        return widget
