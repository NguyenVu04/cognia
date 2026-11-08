"""Memory: what the companion holds, in three groups.

*You told me* holds what the user said about themselves. *I noticed* holds the
companion's conclusions and the patterns it learned, each with its evidence
under it, and the time spent in each application. *About me* holds its own
feeling. Every item shows its date, and can be corrected, removed or undone.
The view is told what to show and reports what the user asked for.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.domain.learning.models import Learned
from src.domain.memory.models import NOTICED, MemoryItem
from src.ui import formatting, theme
from src.ui.widgets.buttons import Button
from src.ui.widgets.layout import clear
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import StyledWidget, card
from src.ui.widgets.typography import (
    body,
    caption,
    heading,
    kicker,
    lede,
    paragraph,
    set_paragraph_text,
)

COLUMN_WIDTH = 680
TEXT_WIDTH = COLUMN_WIDTH - 40

# What each kind of adjustment changes, in plain words.
_CHANGED = {
    "timing": "when I start a chat",
    "frequency": "how often I start a chat",
    "length": "how long my replies are",
    "tone": "how I talk",
}

ALL = "all"
TOLD = "told"
NOTICED_GROUP = "noticed"
ABOUT = "about"
_GROUPS = (
    (ALL, "All"),
    (TOLD, "You told me"),
    (NOTICED_GROUP, "I noticed"),
    (ABOUT, "About me"),
)
_PERIODS = ((0, "Any time"), (7, "Last 7 days"), (30, "Last 30 days"))


class MemoryItemCard(QWidget):
    """One remembered item, with an edit field behind its Edit button."""

    removed = Signal()
    corrected = Signal(str)

    def __init__(
        self,
        text: str,
        date_text: str,
        *,
        remove_label: str,
        evidence: str = "",
        editable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._editing = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = card(padding=(14, 16, 12, 16))
        outer.addWidget(panel)

        self.view = paragraph(text, font=theme.font(14.5), fill=True, selectable=True)
        panel.body().addWidget(self.view)
        self.edit = QLineEdit(text)
        self.edit.setFont(theme.font(14))
        self.edit.setVisible(False)
        self.edit.returnPressed.connect(self._toggle_edit)
        panel.body().addWidget(self.edit)
        if evidence:
            panel.body().addSpacing(8)
            shown = StyledWidget()
            shown.setRules(f"border-left: 2px solid {theme.css(theme.ACCENT_2)};")
            holder = QVBoxLayout(shown)
            holder.setContentsMargins(10, 0, 0, 0)
            holder.addWidget(
                paragraph(
                    evidence,
                    font=theme.font(12.5),
                    colour=theme.TEXT_SECONDARY,
                    fill=True,
                )
            )
            panel.body().addWidget(shown)
        panel.body().addSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(caption(date_text))
        row.addStretch(1)
        self.edit_button = Button("Edit", size="small", variant="ghost")
        self.edit_button.clicked.connect(self._toggle_edit)
        self.edit_button.setVisible(editable)
        row.addWidget(self.edit_button)
        self.remove_button = Button(remove_label, size="small", variant="ghost")
        self.remove_button.clicked.connect(self.removed)
        row.addWidget(self.remove_button)
        panel.body().addLayout(row)

    def _toggle_edit(self) -> None:
        editing = self._editing = not self._editing
        self.edit.setVisible(editing)
        self.view.setVisible(not editing)
        self.edit_button.setText("Done" if editing else "Edit")
        if editing:
            self.edit.setFocus()
            return
        text = " ".join(self.edit.text().split())
        if not text or text == self._text:
            # A blank line is not a correction: the item stays as it was.
            self.edit.setText(self._text)
            return
        set_paragraph_text(self.view, text, font=theme.font(14.5))
        self.corrected.emit(text)


class LearnedCard(QWidget):
    """A pattern the companion learned, its evidence, and what it changed."""

    undoRequested = Signal()
    wrongRequested = Signal()

    def __init__(self, learned: Learned, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = card(padding=(14, 16, 12, 16))
        outer.addWidget(panel)
        panel.body().addWidget(
            paragraph(learned.pattern.statement, font=theme.font(14.5), fill=True)
        )
        panel.body().addSpacing(6)
        times = len(learned.pattern.evidence)
        evidence = f"I noticed this {times} time{'s' if times != 1 else ''}"
        changes = " and ".join(
            _CHANGED[a.aspect] for a in learned.adjustments if a.aspect in _CHANGED
        )
        evidence += f", so I changed {changes}." if changes else "."
        if learned.undone:
            evidence += " You undid this change."
        panel.body().addWidget(
            paragraph(
                evidence, font=theme.font(12.5), colour=theme.TEXT_SECONDARY, fill=True
            )
        )
        panel.body().addSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(caption(formatting.short_date(learned.found_at.date())))
        row.addStretch(1)
        self.undo = Button(
            "Undo", size="small", variant="ghost", icon_name="arrow-counter-clockwise"
        )
        self.undo.setVisible(not learned.undone and bool(learned.adjustments))
        self.undo.clicked.connect(self.undoRequested)
        row.addWidget(self.undo)
        self.wrong = Button("Mark wrong", size="small", variant="ghost")
        self.wrong.clicked.connect(self.wrongRequested)
        row.addWidget(self.wrong)
        panel.body().addLayout(row)


class MemoryView(QWidget):
    removeRequested = Signal(object)
    correctRequested = Signal(object, str)
    undoRequested = Signal(str)
    markWrongRequested = Signal(str)
    feelingWhyRequested = Signal()
    deskSettingsRequested = Signal()
    eraseSettingsRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[MemoryItem] = []
        self._learned: list[Learned] = []
        self._minutes: Mapping[str, int] | None = None
        self._feeling = ""
        self._rest = ""
        self._group = ALL
        self._days = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pane = ScrollPane(padding=(30, 36, 36, 36))
        layout.addWidget(self.pane)
        column = self.pane.column

        column.addWidget(heading("What I remember"))
        column.addSpacing(6)
        column.addWidget(
            lede(
                "Everything I remember about you, and a little about me. It stays "
                "on this computer, and you can change or remove anything.",
            )
        )
        column.addSpacing(18)
        column.addWidget(self._filters(), 0, Qt.AlignmentFlag.AlignLeft)
        column.addSpacing(16)
        self.error = paragraph(
            "", font=theme.font(13.5), colour=theme.DANGER, max_width=COLUMN_WIDTH
        )
        self.error.setVisible(False)
        column.addWidget(self.error)
        self.sections = QVBoxLayout()
        self.sections.setSpacing(10)
        column.addLayout(self.sections)
        column.addSpacing(24)
        erase = Button(
            "Erase memory…", variant="ghost", size="small", icon_name="trash"
        )
        erase.clicked.connect(self.eraseSettingsRequested)
        column.addWidget(erase, 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)

    # ── filters ───────────────────────────────────────────────────────────

    def _filters(self) -> QWidget:
        holder = QWidget()
        holder.setFixedWidth(COLUMN_WIDTH)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search what I remember  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setFont(theme.font(14))
        self.search.textChanged.connect(lambda _: self._render())
        column.addWidget(self.search)
        row = QHBoxLayout()
        row.setSpacing(6)
        self._group_buttons = self._chips(row, _GROUPS, self._set_group)
        row.addSpacing(10)
        self._period_buttons = self._chips(row, _PERIODS, self._set_days)
        row.addStretch(1)
        column.addLayout(row)
        self.filter_bar = QWidget()
        bar = QHBoxLayout(self.filter_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        self.filter_text = body("", px=12.5, colour=theme.ACCENT_TEXT)
        bar.addWidget(self.filter_text)
        clear_button = Button("Clear filter", size="small", variant="ghost")
        clear_button.clicked.connect(self.clearFilter)
        bar.addWidget(clear_button)
        bar.addStretch(1)
        self.filter_bar.setVisible(False)
        column.addWidget(self.filter_bar)
        return holder

    def _chips(self, row: QHBoxLayout, options, choose) -> dict:
        group = QButtonGroup(self)
        buttons = {}
        for value, text in options:
            chip = QPushButton(text)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFont(theme.font(12.5, 600))
            chip.setStyleSheet(
                "QPushButton {"
                f"color: {theme.css(theme.TEXT_SECONDARY)}; background: transparent;"
                f"border: 1px solid {theme.css(theme.BORDER)}; border-radius: 13px;"
                "padding: 4px 11px;"
                "}"
                "QPushButton:checked {"
                f"color: {theme.css(theme.ON_ACCENT)};"
                f"background: {theme.css(theme.ACCENT)};"
                f"border-color: {theme.css(theme.ACCENT)};"
                "}"
            )
            chip.clicked.connect(lambda _=False, v=value: choose(v))
            group.addButton(chip)
            row.addWidget(chip)
            buttons[value] = chip
        next(iter(buttons.values())).setChecked(True)
        return buttons

    def _set_group(self, group: str) -> None:
        self._group = group
        self._render()

    def _set_days(self, days: int) -> None:
        self._days = days
        self._render()

    def clearFilter(self) -> None:
        self.search.clear()
        self._group_buttons[ALL].setChecked(True)
        self._period_buttons[0].setChecked(True)
        self._group, self._days = ALL, 0
        self._render()

    def focusSearch(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    # ── what the application tells it to show ─────────────────────────────

    def setEntries(self, items: Sequence[MemoryItem]) -> None:
        self.error.setVisible(False)
        self._items = list(items)
        self._render()

    def setLearned(self, learned: Sequence[Learned]) -> None:
        self._learned = list(learned)
        self._render()

    def setAppMinutes(self, minutes: Mapping[str, int] | None) -> None:
        """Today's minutes in each application, or ``None`` with desk awareness
        off."""
        self._minutes = minutes
        self._render()

    def setFeeling(self, feeling: str, rest: str) -> None:
        """The feeling now and the resting mood, or "" with moods off."""
        self._feeling, self._rest = feeling, rest
        self._render()

    def showError(self, text: str) -> None:
        """The memory could not be read. No list is shown as though complete."""
        clear(self.sections)
        set_paragraph_text(
            self.error, text, font=theme.font(13.5), max_width=COLUMN_WIDTH
        )
        self.error.setVisible(True)
        self.pane.refresh()

    # ── drawing ───────────────────────────────────────────────────────────

    def _render(self) -> None:
        if self.error.isVisible():
            return
        clear(self.sections)
        query = " ".join(self.search.text().lower().split())
        since = (
            datetime.now().astimezone() - timedelta(days=self._days)
            if self._days
            else None
        )

        def keep(text: str, moment: datetime | None) -> bool:
            if query and query not in text.lower():
                return False
            return since is None or moment is None or moment >= since

        told = [
            i for i in self._items if i.kind != NOTICED and keep(i.text, i.recorded_at)
        ]
        noticed = [
            i
            for i in self._items
            if i.kind == NOTICED and keep(f"{i.text} {i.reason}", i.recorded_at)
        ]
        learned = [x for x in self._learned if keep(x.pattern.statement, x.found_at)]
        groups = (TOLD, NOTICED_GROUP, ABOUT) if self._group == ALL else (self._group,)
        shown = 0
        if TOLD in groups:
            shown += self._section(
                "You told me",
                told,
                self._told_card,
                "Nothing yet. What you tell me about yourself appears here.",
            )
        if NOTICED_GROUP in groups:
            shown += self._section(
                "I noticed",
                noticed,
                self._noticed_card,
                "" if learned else "Nothing noticed yet.",
            )
            for item in learned:
                card_widget = LearnedCard(item)
                card_widget.undoRequested.connect(
                    lambda i=item.id: self.undoRequested.emit(i)
                )
                card_widget.wrongRequested.connect(
                    lambda i=item.id: self.markWrongRequested.emit(i)
                )
                self.sections.addWidget(card_widget)
                shown += 1
            if not query and self._minutes is not None:
                self.sections.addWidget(self._apps_card())
        if ABOUT in groups and not query:
            self.sections.addWidget(kicker("About me"))
            self.sections.addWidget(self._about_card())
        filtered = bool(query) or self._group != ALL or self._days != 0
        self.filter_bar.setVisible(filtered)
        noun = "item" if shown == 1 else "items"
        self.filter_text.setText(f"Filter on · {shown} {noun} shown")
        self.pane.refresh()

    def _section(self, title: str, items, make, empty: str) -> int:
        self.sections.addWidget(kicker(title))
        for item in items:
            self.sections.addWidget(make(item))
        if not items and empty:
            self.sections.addWidget(caption(empty, px=13))
        self.sections.addSpacing(8)
        return len(items)

    def _told_card(self, entry: MemoryItem) -> QWidget:
        widget = MemoryItemCard(entry.text, _day(entry), remove_label="Delete")
        self._connect(widget, entry)
        return widget

    def _noticed_card(self, entry: MemoryItem) -> QWidget:
        widget = MemoryItemCard(
            entry.text,
            _day(entry),
            remove_label="Mark wrong",
            evidence=entry.reason or "",
        )
        self._connect(widget, entry)
        return widget

    def _connect(self, widget: MemoryItemCard, entry: MemoryItem) -> None:
        widget.removed.connect(lambda e=entry: self.removeRequested.emit(e))
        widget.corrected.connect(
            lambda text, e=entry: self.correctRequested.emit(e, text)
        )

    def _apps_card(self) -> QWidget:
        panel = card(padding=(14, 16, 12, 16))
        panel.body().addWidget(body("Time in applications today", weight=700))
        panel.body().addSpacing(6)
        minutes = sorted((self._minutes or {}).items(), key=lambda kv: -kv[1])[:5]
        if not minutes:
            panel.body().addWidget(caption("Nothing recorded yet today.", px=13))
        for name, count in minutes:
            row = QHBoxLayout()
            row.addWidget(body(name))
            row.addStretch(1)
            row.addWidget(body(formatting.duration(count), colour=theme.TEXT_SECONDARY))
            panel.body().addLayout(row)
        panel.body().addSpacing(6)
        manage = Button("Manage in Settings", size="small", variant="ghost")
        manage.clicked.connect(self.deskSettingsRequested)
        panel.body().addWidget(manage, 0, Qt.AlignmentFlag.AlignLeft)
        return panel

    def _about_card(self) -> QWidget:
        panel = card(padding=(14, 16, 12, 16))
        if not self._feeling:
            panel.body().addWidget(
                paragraph(
                    "My moods are switched off, so I'm just calm.",
                    font=theme.font(14.5),
                    fill=True,
                )
            )
            return panel
        panel.body().addWidget(
            paragraph(
                f"I feel {self._feeling} right now. When nothing moves me, "
                f"I come back to {self._rest}.",
                font=theme.font(14.5),
                fill=True,
            )
        )
        panel.body().addSpacing(8)
        why = Button("Why do you feel this way?", size="small", icon_name="question")
        why.clicked.connect(self.feelingWhyRequested)
        panel.body().addWidget(why, 0, Qt.AlignmentFlag.AlignLeft)
        return panel


def _day(entry: MemoryItem) -> str:
    return formatting.short_date(formatting.local_day(entry.recorded_at))
