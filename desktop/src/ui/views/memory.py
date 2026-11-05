"""Memory: review it, correct or remove an item, and erase everything.

Two groups: what the user said, and what the companion noticed. Nothing
appears in the second column without the evidence printed under it, and the
erase strip states the count before anything goes.

The view is told what to show and reports what the user asked for. Whether a
change is kept is decided in ``app/``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from src.domain.memory.models import NOTICED, Commitment, Entry, MemoryItem
from src.ui import theme
from src.ui.widgets.buttons import accent_button, quiet_button, small_button
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import Panel, StyledWidget
from src.ui.widgets.typography import (
    body,
    heading,
    kicker,
    lede,
    paragraph,
    set_paragraph_text,
)

# max-width: 900px in the design, but the content column is only this wide.
COLUMNS_WIDTH = 716
COLUMN_WIDTH = (COLUMNS_WIDTH - 26) // 2

MEMORY = "memory"
EVERYTHING = "everything"

_ENGLISH = QLocale(QLocale.Language.English)


def short_day(day: date) -> str:
    """For example "5 Nov". The companion speaks English only."""
    return _ENGLISH.toString(day, "d MMM")


def _local_day(moment: datetime) -> date:
    return moment.astimezone().date()


class MemoryItemCard(Panel):
    """One remembered item, with an inline edit field behind an Edit button."""

    removed = Signal()
    corrected = Signal(str)

    def __init__(
        self,
        text: str,
        date_text: str,
        *,
        remove_label: str,
        evidence: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            fill=theme.BG_CARD, ring=theme.BORDER_SUBTLE, radius=9,
            padding=(14, 16, 14, 16), parent=parent,
        )
        self._text = text
        self._editing = False

        self.view = paragraph(
            text, font=theme.font(13.8), colour=theme.TEXT,
            line_height=1.55, fill=True,
        )
        self.body().addWidget(self.view)

        self.edit = QLineEdit(text)
        self.edit.setFont(theme.font(13.5))
        self.edit.setStyleSheet(
            "QLineEdit {"
            f"border-radius: 6px; padding: 7px 9px;"
            f"border: 1px solid {theme.css(theme.ACCENT)};"
            "}"
        )
        self.edit.setVisible(False)
        self.edit.returnPressed.connect(self._toggle_edit)
        self.body().addWidget(self.edit)

        if evidence:
            self.body().addSpacing(9)
            shown = StyledWidget()
            shown.setRules(
                f"border-left: 2px solid {theme.css(theme.wash(0.5))};"
            )
            holder = QVBoxLayout(shown)
            holder.setContentsMargins(11, 0, 0, 0)
            holder.setSpacing(0)
            holder.addWidget(
                paragraph(
                    evidence, font=theme.font(12),
                    colour=theme.muted(0.5), line_height=1.5, fill=True,
                )
            )
            self.body().addWidget(shown)

        self.body().addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(body(date_text, px=11.5, alpha=0.4))
        row.addStretch(1)
        self.edit_button = small_button("Edit")
        self.edit_button.clicked.connect(self._toggle_edit)
        row.addWidget(self.edit_button)
        self.remove_button = small_button(remove_label)
        self.remove_button.clicked.connect(self.removed)
        row.addWidget(self.remove_button)
        self.body().addLayout(row)

    def _toggle_edit(self) -> None:
        editing = self._editing = not self._editing
        self.edit.setVisible(editing)
        self.view.setVisible(not editing)
        self.edit_button.setLabel("Done" if editing else "Edit")
        if editing:
            self.edit.setFocus()
            return
        text = " ".join(self.edit.text().split())
        if not text or text == self._text:
            # A blank line is not a correction: the item stays as it was.
            self.edit.setText(self._text)
            return
        set_paragraph_text(self.view, text, font=theme.font(13.8), line_height=1.55)
        self.corrected.emit(text)


class MemoryView(QWidget):
    #: The entry the user wants gone.
    removeRequested = Signal(object)
    #: The entry and its new words.
    correctRequested = Signal(object, str)
    #: ``"memory"`` or ``"everything"``.
    eraseRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = ""
        self._count = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.pane = ScrollPane(padding=(34, 40, 40, 40))
        layout.addWidget(self.pane)
        column = self.pane.column

        column.addWidget(heading("What I remember"))
        column.addSpacing(4)
        column.addWidget(
            lede(
                "Everything held about you, on your disk. Two groups: what you "
                "told me, and what I noticed — and nothing appears in the "
                "second without the evidence under it.",
                max_width=600,
            )
        )
        column.addSpacing(26)
        self.columns = self._columns()
        column.addWidget(self.columns, 0, Qt.AlignmentFlag.AlignLeft)
        self.error = paragraph(
            "", font=theme.font(13.5), colour=theme.muted(0.7), max_width=600
        )
        self.error.setVisible(False)
        column.addWidget(self.error, 0, Qt.AlignmentFlag.AlignLeft)
        column.addSpacing(32)
        column.addWidget(self._erase_strip(), 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)

    # ── what the application tells it to show ─────────────────────────────

    def setEntries(  # noqa: N802 - matches Qt naming
        self, items: Sequence[MemoryItem], commitments: Sequence[Commitment]
    ) -> None:
        """Show every item: what the user said and their commitments under *you
        told me*, the companion's conclusions under *I noticed*."""
        self.error.setVisible(False)
        self.columns.setVisible(True)
        told = [i for i in items if i.kind != NOTICED]
        noticed = [i for i in items if i.kind == NOTICED]
        self._fill(self._told, [*told, *commitments], "Delete")
        self._fill(self._noticed, noticed, "Wrong")
        self._count = len(items) + len(commitments)
        self._update_strip()
        self.pane.refresh()

    def showError(self, text: str) -> None:  # noqa: N802 - matches Qt naming
        """The memory could not be read. No list is shown as though complete."""
        self.columns.setVisible(False)
        set_paragraph_text(self.error, text, font=theme.font(13.5), max_width=600)
        self.error.setVisible(True)
        self.pane.refresh()

    def setCharacterName(self, name: str) -> None:  # noqa: N802 - Qt naming
        self._name = name
        self._update_strip()

    # ── building ──────────────────────────────────────────────────────────

    def _columns(self) -> QWidget:
        holder = QWidget()
        holder.setFixedWidth(COLUMNS_WIDTH)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(26)
        told, self._told = self._group("You told me")
        noticed, self._noticed = self._group("I noticed")
        row.addWidget(told, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(noticed, 0, Qt.AlignmentFlag.AlignTop)
        return holder

    def _group(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        group = QWidget()
        group.setFixedWidth(COLUMN_WIDTH)
        column = QVBoxLayout(group)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(kicker(title))
        column.addSpacing(12)
        cards = QVBoxLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(10)
        column.addLayout(cards)
        column.addStretch(1)
        return group, cards

    def _fill(
        self, cards: QVBoxLayout, entries: Sequence[Entry], remove_label: str
    ) -> None:
        while cards.count():
            widget = cards.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for entry in entries:
            card = MemoryItemCard(
                entry.text,
                _date_text(entry),
                remove_label=remove_label,
                evidence=(entry.reason or "") if isinstance(entry, MemoryItem) else "",
            )
            card.removed.connect(lambda e=entry: self.removeRequested.emit(e))
            card.corrected.connect(
                lambda text, e=entry: self.correctRequested.emit(e, text)
            )
            cards.addWidget(card)

    def _erase_strip(self) -> Panel:
        strip = Panel(
            fill=theme.wash(0.06), ring=theme.wash(0.22), radius=10,
            padding=(16, 20, 16, 20),
        )
        strip.setFixedWidth(COLUMNS_WIDTH)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.strip_text = paragraph(
            "", font=theme.font(13), colour=theme.muted(0.7), line_height=1.55,
            fill=True,
        )
        row.addWidget(self.strip_text, 1)
        self.erase_memory = quiet_button(
            "Erase memory", px=12.5, radius=7, padding=(9, 14), fg=theme.muted(0.75)
        )
        self.erase_memory.clicked.connect(lambda: self.eraseRequested.emit(MEMORY))
        row.addWidget(self.erase_memory)
        self.erase_everything = accent_button(
            "Erase everything", px=12.5, weight=400, radius=7, padding=(9, 14)
        )
        self.erase_everything.clicked.connect(
            lambda: self.eraseRequested.emit(EVERYTHING)
        )
        row.addWidget(self.erase_everything)
        strip.body().addLayout(row)
        self._update_strip()
        return strip

    def _update_strip(self) -> None:
        keep = f"keep {self._name}" if self._name else "keep the character"
        set_paragraph_text(
            self.strip_text,
            f"Erase everything remembered ({self._count} items) and {keep} — or "
            "erase without exception. You are told the count before anything "
            "goes.",
            font=theme.font(13),
            line_height=1.55,
        )


def _date_text(entry: Entry) -> str:
    told = short_day(_local_day(entry.recorded_at))
    if isinstance(entry, Commitment) and entry.due_on is not None:
        return f"{told} · due {short_day(entry.due_on)}"
    return told
