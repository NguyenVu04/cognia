"""First run — UC-01 and UC-02.

Four ready-made characters and a blank box, and nothing chosen for the user:
an unchosen companion is not a companion. This view takes the whole window,
without the sidebar.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)

from src.ui import theme
from src.ui.views import sample_data
from src.ui.widgets.buttons import LayoutButton, accent_button
from src.ui.widgets.hatch import HatchPanel
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.typography import body, eyebrow, label, paragraph

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
                "Pick one to hear it answer, or write your own. Nothing is "
                "chosen for you — an unchosen companion is not a companion.",
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
        column.addSpacing(28)

        column.addLayout(self._own_words())
        column.addStretch(1)
        column.addSpacing(32)
        column.addLayout(self._confirm_row())

        self._select(self._cards[0])

    def _own_words(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(28)

        left = QVBoxLayout()
        left.setSpacing(0)
        caption = QHBoxLayout()
        caption.setSpacing(4)
        caption.addWidget(body("Or write your own", px=13, weight=500))
        caption.addWidget(
            body("— plain words, no syntax (UC-02)", px=13, alpha=0.45)
        )
        caption.addStretch(1)
        left.addLayout(caption)
        left.addSpacing(8)

        editor = QTextEdit()
        editor.setPlaceholderText(
            "A patient archivist called Wren. Speaks in short sentences, never "
            "flatters, asks one thing at a time."
        )
        editor.setFont(theme.font(13.5))
        editor.setFixedHeight(76)
        editor.setStyleSheet("QTextEdit { border-radius: 8px; padding: 11px 13px; }")
        left.addWidget(editor)
        row.addLayout(left, 1)

        aside = QVBoxLayout()
        aside.setContentsMargins(0, 26, 0, 0)
        aside.addWidget(
            paragraph(
                "A character sets who the companion is and how it speaks. It "
                "can never drop the seven base rules or the safety behaviour.",
                font=theme.font(12.5), colour=theme.muted(0.5),
                line_height=1.6, max_width=300,
            )
        )
        aside.addStretch(1)
        holder = QWidget()
        holder.setFixedWidth(300)
        holder.setLayout(aside)
        row.addWidget(holder, 0, Qt.AlignmentFlag.AlignTop)
        return row

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
