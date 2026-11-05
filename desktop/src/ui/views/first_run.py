"""Choosing a character: at first run, and again to change it.

Four ready-made characters, and nothing chosen for the user: an unchosen
companion is not a companion. A card shows one line in the character's voice;
the picked card shows its whole written answer to "What should I expect from
you?". This view takes the whole window, without the sidebar.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.domain.character.models import Template
from src.ui import theme
from src.ui.widgets.buttons import LayoutButton, accent_button, quiet_button
from src.ui.widgets.hatch import HatchPanel
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import Panel
from src.ui.widgets.typography import eyebrow, label, paragraph

# Four columns across the 898px content box with 16px gaps, less the card's
# 16px padding and 1px ring on each side.
CARD_WIDTH = (898 - 3 * 16) // 4
CARD_INNER = CARD_WIDTH - 34
SAMPLE_WIDTH = 620


class CharacterCard(LayoutButton):
    """A pickable character. Selection shows as an accent ring and a wash."""

    def __init__(
        self, template: Template, *, in_force: bool, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.template = template
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
            label(template.name, font=theme.font(16, 500), colour=theme.TEXT)
        )
        names.addWidget(
            label(template.role, font=theme.font(12.5), colour=theme.muted(0.5))
        )
        if in_force:
            names.addWidget(eyebrow("In force", px=10.5))
        column.addLayout(names)

        sample_font = theme.font(12.5)
        sample_font.setItalic(True)
        # A fixed width rather than fill: a grid row's minimum height ignores
        # heightForWidth, so a filling label lets the row squeeze the card.
        quote = paragraph(
            f"“{template.card_line}”",
            font=sample_font, colour=theme.muted(0.72), line_height=1.5,
            max_width=CARD_INNER,
        )
        quote.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        column.addWidget(quote)
        # Cards in a row share the tallest one's height; the surplus belongs
        # at the bottom, not spread through the stack.
        column.addStretch(1)

        self.setEnabled(not in_force)
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
    #: The id of the template the user confirmed.
    confirmed = Signal(str)
    #: Leave without changing the character.
    backRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards: list[CharacterCard] = []
        self._picked: CharacterCard | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.pane = ScrollPane(padding=(44, 56, 44, 56))
        layout.addWidget(self.pane)
        column = self.pane.column

        self.eyebrow = eyebrow("First run")
        column.addWidget(self.eyebrow)
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

        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        column.addLayout(self.grid)
        column.addSpacing(20)
        column.addWidget(self._sample_panel(), 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)
        column.addSpacing(32)
        column.addLayout(self._confirm_row())
        self.error = label("", font=theme.font(12.5), colour=theme.muted(0.7))
        self.error.setVisible(False)
        column.addWidget(self.error)

    # ── what the application tells it to show ─────────────────────────────

    def setTemplates(  # noqa: N802 - matches Qt naming
        self, templates: Sequence[Template], in_force: str | None
    ) -> None:
        """Show the ready-made characters. ``in_force`` is the template of the
        character in force, which cannot be picked again, or ``None`` at first
        run."""
        for card in self._cards:
            self.grid.removeWidget(card)
            card.deleteLater()
        self._cards = []
        for index, template in enumerate(templates):
            card = CharacterCard(template, in_force=template.id == in_force)
            card.clicked.connect(lambda _=False, c=card: self._select(c))
            self.grid.addWidget(card, 0, index)
            self._cards.append(card)
        self.eyebrow.setText("First run" if in_force is None else "Change character")
        self.back.setVisible(in_force is not None)
        self.error.setVisible(False)
        self._select(None)

    def showError(self, text: str) -> None:  # noqa: N802 - matches Qt naming
        self.error.setText(text)
        self.error.setVisible(True)

    # ── building ──────────────────────────────────────────────────────────

    def _sample_panel(self) -> Panel:
        self.sample = Panel(
            fill=theme.BG_CARD, ring=theme.BORDER_SUBTLE, radius=10,
            padding=(16, 20, 16, 20),
        )
        self.sample.setFixedWidth(SAMPLE_WIDTH + 42)
        self.sample.body().addWidget(eyebrow("What should I expect from you?"))
        self.sample.body().addSpacing(8)
        self.sample_lines = QVBoxLayout()
        self.sample_lines.setSpacing(8)
        self.sample.body().addLayout(self.sample_lines)
        self.sample.setVisible(False)
        return self.sample

    def _show_sample(self, answer: str) -> None:
        """One paragraph for each block of the written answer."""
        while self.sample_lines.count():
            widget = self.sample_lines.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for block in answer.strip().split("\n\n"):
            self.sample_lines.addWidget(
                paragraph(
                    " ".join(block.split()), font=theme.font(13.5),
                    colour=theme.muted(0.78), line_height=1.6,
                    max_width=SAMPLE_WIDTH,
                )
            )

    def _confirm_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)
        self.confirm = accent_button("Confirm", px=14, radius=8, padding=(10, 22))
        self.confirm.clicked.connect(self._confirm)
        row.addWidget(self.confirm)
        self.back = quiet_button("Back", px=14, radius=8, padding=(10, 18))
        self.back.clicked.connect(self.backRequested)
        self.back.setVisible(False)
        row.addWidget(self.back)
        row.addWidget(
            label(
                "Nothing is saved until you confirm.",
                font=theme.font(12.5), colour=theme.muted(0.45),
            )
        )
        row.addStretch(1)
        return row

    def _select(self, chosen: CharacterCard | None) -> None:
        self._picked = chosen
        for card in self._cards:
            card.setActive(card is chosen)
        self.confirm.setEnabled(chosen is not None)
        if chosen is None:
            self.confirm.setLabel("Confirm")
            self.sample.setVisible(False)
            return
        template = chosen.template
        self.confirm.setLabel(f"Confirm {template.name}")
        self._show_sample(template.sample_answer)
        self.sample.setVisible(True)
        self.pane.refresh()

    def _confirm(self) -> None:
        if self._picked is not None:
            self.confirmed.emit(self._picked.template.id)
