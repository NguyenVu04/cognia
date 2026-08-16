"""Desk awareness — UC-04.

Off until switched on, and the two lists are the point of the screen: exactly
the three facts C-05 permits on the left, and the things that are never read on
the right.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from src.ui import icons, theme
from src.ui.views import sample_data
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import Panel, bottom_rule
from src.ui.widgets.toggle import PillToggle
from src.ui.widgets.typography import eyebrow, heading, label, lede, paragraph

# max-width: 820px in the design, capped by the real content column.
GRID_WIDTH = 716
CARD_WIDTH = (GRID_WIDTH - 22) // 2


class DeskView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        pane = ScrollPane(padding=(34, 40, 40, 40))
        layout.addWidget(pane)
        column = pane.column

        column.addWidget(eyebrow("UC-04"))
        column.addSpacing(6)
        column.addWidget(heading("Desk awareness"))
        column.addSpacing(4)
        column.addWidget(
            lede(
                "Off until you switch it on. Turning it down costs you nothing "
                "— conversation works in full either way.",
                max_width=600,
            )
        )
        column.addSpacing(28)

        grid = QWidget()
        grid.setFixedWidth(GRID_WIDTH)
        row = QHBoxLayout(grid)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(22)
        row.addWidget(
            self._list_card("What it reads", "check-circle", theme.ACCENT_TEXT,
                            sample_data.READS, 0.8)
        )
        row.addWidget(
            self._list_card("What it never reads", "prohibit", theme.muted(0.55),
                            sample_data.NEVER_READS, 0.5)
        )
        column.addWidget(grid, 0, Qt.AlignmentFlag.AlignLeft)

        column.addSpacing(26)
        column.addWidget(self._state_row(), 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)

    def _list_card(
        self, title: str, icon_name: str, title_colour, entries: list[str], alpha: float
    ) -> Panel:
        card = Panel(
            fill=theme.BG_CARD, ring=theme.BORDER_SUBTLE, radius=10,
            padding=(20, 22, 20, 22),
        )
        card.setFixedWidth(CARD_WIDTH)

        header = QHBoxLayout()
        header.setSpacing(7)
        header.addWidget(icons.icon_label(icon_name, 13, title_colour))
        header.addWidget(
            label(title, font=theme.font(13, 500), colour=title_colour)
        )
        header.addStretch(1)
        card.body().addLayout(header)
        card.body().addSpacing(12)

        for entry in entries:
            line = bottom_rule()
            holder = QVBoxLayout(line)
            holder.setContentsMargins(0, 7, 0, 7)
            holder.setSpacing(0)
            holder.addWidget(
                paragraph(entry, font=theme.font(13.5),
                          colour=theme.muted(alpha), line_height=1.55,
                          fill=True)
            )
            card.body().addWidget(line)
        # The shorter card is stretched to the taller one's height; the
        # surplus belongs under the last row, not between the rows.
        card.body().addStretch(1)
        return card

    def _state_row(self) -> Panel:
        card = Panel(
            fill=theme.BG_CARD, ring=theme.BORDER, radius=10,
            padding=(18, 22, 18, 22),
        )
        card.setFixedWidth(GRID_WIDTH)

        row = QHBoxLayout()
        row.setSpacing(16)
        text = QVBoxLayout()
        text.setSpacing(3)
        self.state_label = label(
            "Desk awareness is on", font=theme.font(15, 500), colour=theme.TEXT
        )
        text.addWidget(self.state_label)
        text.addWidget(
            label(
                "It knows only whether you are at the machine — never what you "
                "are doing.",
                font=theme.font(12.5), colour=theme.muted(0.5),
            )
        )
        row.addLayout(text, 1)

        self.toggle = PillToggle("large", checked=True)
        self.toggle.toggled.connect(
            lambda on: self.state_label.setText(
                f"Desk awareness is {'on' if on else 'off'}"
            )
        )
        row.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        card.body().addLayout(row)
        return card
