"""First run — UC-01.

Four ready-made characters, and nothing chosen for the user: an unchosen
companion is not a companion. This view takes the whole window, without the
sidebar.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.ui import theme
from src.ui.views import sample_data
from src.ui.widgets.buttons import LayoutButton, accent_button
from src.ui.widgets.hatch import HatchPanel
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.typography import eyebrow, label, paragraph

# Four columns across the 898px content box with 16px gaps, less the card's
# 16px padding and 1px ring on each side.
CARD_WIDTH = (898 - 3 * 16) // 4
CARD_INNER = CARD_WIDTH - 34


class CharacterCard(LayoutButton):
    """A pickable character. Selection shows as an accent ring and a wash."""

    def __init__(
        self, character: sample_data.Character, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.character = character
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        # Grid items share the tallest card's height; a button is vertically
        # Fixed by default, which would centre a short card in its row.
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )

        column = QVBoxLayout(self)
        column.setContentsMargins(16, 16, 16, 16)
        column.setSpacing(12)

        sprite = HatchPanel("sprite\n320×420", radius=8)
        sprite.setFixedHeight(132)
        sprite.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        column.addWidget(sprite)

        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(
            label(character.name, font=theme.font(16, 500), colour=theme.TEXT)
        )
        names.addWidget(
            label(character.role, font=theme.font(12.5), colour=theme.muted(0.5))
        )
        column.addLayout(names)

        sample_font = theme.font(12.5)
        sample_font.setItalic(True)
        # A fixed width rather than fill: a grid row's minimum height ignores
        # heightForWidth, so a filling label lets the row squeeze the card.
        quote = paragraph(
            f"“{character.sample}”",
            font=sample_font, colour=theme.muted(0.72), line_height=1.5,
            max_width=CARD_INNER,
        )
        quote.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        column.addWidget(quote)
        # Cards in a row share the tallest one's height; the surplus belongs
        # at the bottom, not spread through the stack.
        column.addStretch(1)

        self.setActive(False)

    def setActive(self, active: bool) -> None:  # noqa: N802 - matches Qt naming
        self.setChecked(active)
        fill = theme.wash(0.09) if active else theme.BG_CARD
        ring = theme.ACCENT if active else theme.BORDER_SUBTLE
        self.setStyleSheet(
            "QPushButton {"
            f"border-radius: 10px; border: 1px solid {theme.css(ring)};"
            f"background: {theme.css(fill)}; text-align: left;"
            "}"
        )


class FirstRunView(QWidget):
    confirmed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        pane = ScrollPane(padding=(44, 56, 44, 56))
        layout.addWidget(pane)
        column = pane.column

        column.addWidget(eyebrow("First run · UC-01"))
        column.addSpacing(10)
        column.addWidget(
            label(
                "Who is sitting with you?",
                font=theme.font(32, 500, spacing_em=-0.015), colour=theme.TEXT,
            )
        )
        column.addSpacing(8)
        column.addWidget(
            paragraph(
                "Pick one to hear it answer. Nothing is chosen for you — an "
                "unchosen companion is not a companion.",
                font=theme.font(15), colour=theme.muted(0.6),
                line_height=1.55, max_width=620,
            )
        )
        column.addSpacing(28)

        grid = QGridLayout()
        grid.setSpacing(16)
        self._cards: list[CharacterCard] = []
        for index, character in enumerate(sample_data.CHARACTERS):
            card = CharacterCard(character)
            card.clicked.connect(lambda _=False, c=card: self._select(c))
            grid.addWidget(card, 0, index)
            self._cards.append(card)
        column.addLayout(grid)
        column.addStretch(1)
        column.addSpacing(32)
        column.addLayout(self._confirm_row())

        self._select(self._cards[0])

    def _confirm_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)
        self.confirm = accent_button("Confirm Wren", px=14, radius=8, padding=(10, 22))
        self.confirm.clicked.connect(self.confirmed)
        row.addWidget(self.confirm)
        row.addWidget(
            label(
                "Nothing is saved until you confirm.",
                font=theme.font(12.5), colour=theme.muted(0.45),
            )
        )
        row.addStretch(1)
        return row

    def _select(self, chosen: CharacterCard) -> None:
        for card in self._cards:
            card.setActive(card is chosen)
        self.confirm.setLabel(f"Confirm {chosen.character.name}")
