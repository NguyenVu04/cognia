"""Confirming an erasure, and saying what it removed.

The count comes before anything goes, because erasure cannot be undone. Afterwards
the dialog says exactly what was and was not removed, and never calls a partial
erasure complete.

This dialog was added beyond the designed screens: the design shows the erase
strip and its two buttons, but not the step after them.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from src.domain.erasure.models import ErasureReport, Group, GroupCount, Level
from src.ui import theme
from src.ui.widgets.buttons import accent_button, quiet_button
from src.ui.widgets.shadow import ShadowWindow
from src.ui.widgets.surface import bottom_rule
from src.ui.widgets.typography import body, label, paragraph

WIDTH = 460
TEXT_WIDTH = WIDTH - 56

GROUP_NAMES = {
    Group.CONVERSATIONS: "Messages in conversations",
    Group.MEMORY: "Things you told me",
    Group.DESK: "Time spent in each application",
    Group.LEARNING: "Patterns I learned",
    Group.SPEECH: "Records of when I spoke",
    Group.EVENTS: "Recorded events and feelings",
    Group.CHARACTER: "Character versions",
    Group.SETTINGS: "Settings, back to their defaults",
}


class EraseDialog(ShadowWindow):
    confirmed = Signal()
    retryRequested = Signal()

    def __init__(
        self,
        level: Level,
        counts: Sequence[GroupCount],
        character_name: str | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            radius=12, fill=theme.BG_CARD, ring=theme.BORDER, blur=48, dy=20,
            shadow_colour=theme.SHADOW.darker(), margin=40,
            flags=Qt.WindowType.Dialog, parent=parent,
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("Erase")
        self.body.setFixedWidth(WIDTH)
        self._level = level
        self._name = character_name or "the character"

        frame = self.body.body()
        frame.setContentsMargins(28, 24, 28, 22)
        frame.setSpacing(0)
        self.content = QVBoxLayout()
        self.content.setSpacing(0)
        frame.addLayout(self.content)
        frame.addSpacing(20)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(10)
        frame.addLayout(self.buttons)

        self._show_counts(counts)

    # ── states ────────────────────────────────────────────────────────────

    def _show_counts(self, counts: Sequence[GroupCount]) -> None:
        shown = [c for c in counts if c.rows > 0]
        total = sum(c.rows for c in shown)
        everything = self._level is Level.EVERYTHING
        self._title("Erase everything?" if everything else "Erase memory?")
        if everything:
            self._text(f"Everything goes, without exception — {self._name} too.")
        else:
            self._text(
                "Everything remembered goes, what I hold about myself included. "
                f"{self._name.capitalize()} and your settings stay."
            )
        if not shown:
            self._text("There is nothing to erase.")
            self._button(quiet_button("Close"), self.close)
            return
        self.content.addSpacing(14)
        for count in shown:
            self.content.addWidget(self._group_row(count))
        self.content.addSpacing(14)
        self._text("This cannot be undone.")
        self.buttons.addStretch(1)
        self._button(quiet_button("Cancel"), self.close)
        noun = "item" if total == 1 else "items"
        self.erase = self._button(
            accent_button(f"Erase {total} {noun}"), self.confirmed.emit
        )

    def showWorking(self) -> None:  # noqa: N802 - matches Qt naming
        self._clear()
        self._title("Erasing…")
        self._text("This can take a moment while the file is rewritten.")

    def showReport(self, report: ErasureReport) -> None:  # noqa: N802 - Qt naming
        """What is gone, and what is not. A partial erasure offers to run again."""
        self._clear()
        if report.complete:
            self._title("Erased")
            self._text("Nothing of it remains on the disk.")
            self.buttons.addStretch(1)
            self._button(accent_button("Close"), self.close)
            return
        self._title("Not everything was erased")
        if report.erased:
            self._text("Removed: " + _names(report.erased) + ".")
        if report.failed:
            self._text("Not removed: " + _names(report.failed) + ".")
        if not report.compacted:
            self._text(
                "The data file could not be rewritten, so removed rows may still "
                "be in it."
            )
        self.buttons.addStretch(1)
        self._button(quiet_button("Close"), self.close)
        self.retry = self._button(accent_button("Try again"), self.retryRequested.emit)

    def showStopped(self) -> None:  # noqa: N802 - matches Qt naming
        """The erasure ended with no report, so nobody knows which groups went.
        Running it again erases whatever is left."""
        self._clear()
        self._title("Not everything was erased")
        self._text("Erasing stopped partway, so some of it may still be on the disk.")
        self.buttons.addStretch(1)
        self._button(quiet_button("Close"), self.close)
        self.retry = self._button(accent_button("Try again"), self.retryRequested.emit)

    # ── building ──────────────────────────────────────────────────────────

    def _clear(self) -> None:
        for layout in (self.content, self.buttons):
            while layout.count():
                item = layout.takeAt(0)
                if (widget := item.widget()) is not None:
                    widget.deleteLater()

    def _title(self, text: str) -> None:
        self.content.addWidget(label(text, font=theme.font(18, 500), colour=theme.TEXT))
        self.content.addSpacing(8)

    def _text(self, text: str) -> None:
        self.content.addWidget(
            paragraph(
                text, font=theme.font(13.5), colour=theme.muted(0.7),
                line_height=1.55, max_width=TEXT_WIDTH,
            )
        )
        self.content.addSpacing(6)

    def _group_row(self, count: GroupCount) -> QWidget:
        widget = bottom_rule()
        row = QHBoxLayout(widget)
        row.setContentsMargins(2, 8, 2, 8)
        row.addWidget(body(GROUP_NAMES[count.group], px=13.5, alpha=0.8))
        row.addStretch(1)
        if count.group is not Group.SETTINGS:
            row.addWidget(body(f"{count.rows:,}", px=13, alpha=0.6))
        return widget

    def _button(self, button, action):
        button.clicked.connect(lambda: action())
        self.buttons.addWidget(button)
        return button

    def centre_on(self, widget: QWidget) -> None:
        """Place the dialog over the middle of ``widget``."""
        self.adjustSize()
        centre = widget.mapToGlobal(widget.rect().center())
        self.move(centre - self.rect().center())


def _names(groups: Sequence[Group]) -> str:
    return ", ".join(GROUP_NAMES[group].lower() for group in groups)
