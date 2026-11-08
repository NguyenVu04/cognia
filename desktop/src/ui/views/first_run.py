"""Choosing a character: at first run, and again to change it.

Four ready-made characters, and nothing chosen for the user. A card shows the
character's face and one line in its voice; the picked card shows its whole
written answer to "What should I expect from you?". This view takes the whole
window, without the sidebar.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.domain.character.models import Template
from src.ui import theme
from src.ui.widgets.buttons import Button, LayoutButton
from src.ui.widgets.layout import clear
from src.ui.widgets.portrait import portrait
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import Panel, card
from src.ui.widgets.typography import caption, kicker, label, lede, paragraph

CARD_WIDTH = 214
PORTRAIT = QSize(CARD_WIDTH - 26, 168)
SAMPLE_WIDTH = 640


class CharacterCard(LayoutButton):
    """A pickable character. Selection shows as an accent ring and a wash."""

    def __init__(
        self, template: Template, *, in_force: bool, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.template = template
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setFixedWidth(CARD_WIDTH)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.MinimumExpanding
        )
        self.setAccessibleName(f"{template.name}, {template.role}")
        column = QVBoxLayout(self)
        column.setContentsMargins(12, 12, 12, 14)
        column.setSpacing(10)

        picture = QLabel()
        picture.setFixedSize(PORTRAIT)
        picture.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        pixmap = portrait(template.appearance_id, PORTRAIT)
        if pixmap is not None:
            picture.setPixmap(pixmap)
        picture.setStyleSheet(
            f"background: {theme.css(theme.BG_INSET)}; border-radius: 10px;"
        )
        column.addWidget(picture)

        names = QVBoxLayout()
        names.setSpacing(1)
        names.addWidget(label(template.name, font=theme.font(17, 800)))
        names.addWidget(
            label(template.role, font=theme.font(12.5), colour=theme.TEXT_SECONDARY)
        )
        if in_force:
            names.addWidget(kicker("In force"))
        column.addLayout(names)

        quote_font = theme.font(13)
        quote_font.setItalic(True)
        quote = paragraph(
            f"“{template.card_line}”",
            font=quote_font,
            colour=theme.TEXT_SECONDARY,
            max_width=CARD_WIDTH - 26,
        )
        quote.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        column.addWidget(quote)
        column.addStretch(1)
        self.setEnabled(not in_force)
        self.setActive(False)

    def setActive(self, active: bool) -> None:
        self.setChecked(active)
        fill = theme.wash(0.10) if active else theme.BG_CARD
        ring = theme.ACCENT if active else theme.BORDER_SUBTLE
        self.setStyleSheet(
            "QPushButton {"
            f"border-radius: 14px; border: {2 if active else 1}px solid "
            f"{theme.css(ring)}; background: {theme.css(fill)}; text-align: left;"
            "}"
            f"QPushButton:hover {{ border-color: {theme.css(theme.ACCENT)}; }}"
            f"QPushButton:focus {{ outline: none; border-color: "
            f"{theme.css(theme.ACCENT_2)}; }}"
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
        self.pane = ScrollPane(padding=(36, 44, 36, 44))
        layout.addWidget(self.pane)
        column = self.pane.column

        self.eyebrow = kicker("Welcome")
        column.addWidget(self.eyebrow)
        column.addSpacing(8)
        self.headline = label(
            "Who would you like beside you?", font=theme.font(30, 800)
        )
        column.addWidget(self.headline)
        column.addSpacing(8)
        column.addWidget(
            lede(
                "Pick one to read how they answer. Nothing is chosen for you, and "
                "you can change your mind later in Character.",
                max_width=640,
            )
        )
        column.addSpacing(24)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(14)
        column.addLayout(self.grid)
        column.addSpacing(18)
        column.addWidget(self._sample_panel(), 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)
        column.addSpacing(24)
        column.addLayout(self._confirm_row())
        self.error = label("", font=theme.font(13), colour=theme.DANGER, wrap=True)
        self.error.setVisible(False)
        column.addWidget(self.error)

    # ── what the application tells it to show ─────────────────────────────

    def setTemplates(self, templates: Sequence[Template], in_force: str | None) -> None:
        """Show the ready-made characters. ``in_force`` is the template of the
        character in force, which cannot be picked again, or ``None`` at first
        run."""
        for old in self._cards:
            self.grid.removeWidget(old)
            old.deleteLater()
        self._cards = []
        for index, template in enumerate(templates):
            choice = CharacterCard(template, in_force=template.id == in_force)
            choice.clicked.connect(lambda _=False, c=choice: self._select(c))
            self.grid.addWidget(choice, 0, index)
            self._cards.append(choice)
        first = in_force is None
        self.eyebrow.setText("WELCOME" if first else "CHANGE CHARACTER")
        self.headline.setText(
            "Who would you like beside you?" if first else "Choose another character"
        )
        self.back.setVisible(not first)
        self.error.setVisible(False)
        self._select(None)

    def showError(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(True)

    # ── building ──────────────────────────────────────────────────────────

    def _sample_panel(self) -> Panel:
        self.sample = card(padding=(16, 20, 16, 20))
        self.sample.setFixedWidth(SAMPLE_WIDTH + 42)
        self.sample_title = kicker("What should I expect from you?")
        self.sample.body().addWidget(self.sample_title)
        self.sample.body().addSpacing(8)
        self.sample_lines = QVBoxLayout()
        self.sample_lines.setSpacing(8)
        self.sample.body().addLayout(self.sample_lines)
        self.sample.setVisible(False)
        return self.sample

    def _show_sample(self, answer: str) -> None:
        """One paragraph for each block of the written answer."""
        clear(self.sample_lines)
        for block in answer.strip().split("\n\n"):
            self.sample_lines.addWidget(
                paragraph(
                    " ".join(block.split()),
                    font=theme.font(14),
                    max_width=SAMPLE_WIDTH,
                )
            )

    def _confirm_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        self.confirm = Button("Confirm", variant="primary", icon_name="check")
        self.confirm.clicked.connect(self._confirm)
        row.addWidget(self.confirm)
        self.back = Button("Back")
        self.back.clicked.connect(self.backRequested)
        self.back.setVisible(False)
        row.addWidget(self.back)
        row.addWidget(caption("Nothing is saved until you confirm."))
        row.addStretch(1)
        return row

    def _select(self, chosen: CharacterCard | None) -> None:
        self._picked = chosen
        for each in self._cards:
            each.setActive(each is chosen)
        self.confirm.setEnabled(chosen is not None)
        if chosen is None:
            self.confirm.setText("Confirm")
            self.sample.setVisible(False)
            return
        template = chosen.template
        self.confirm.setText(f"Choose {template.name}")
        self._show_sample(template.sample_answer)
        self.sample.setVisible(True)
        self.pane.refresh()

    def _confirm(self) -> None:
        if self._picked is not None:
            self.confirmed.emit(self._picked.template.id)
