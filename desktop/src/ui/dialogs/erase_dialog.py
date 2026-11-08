"""Confirming an erasure, and saying what it removed.

The count comes before anything goes, because erasure cannot be undone.
Afterwards the dialog says exactly what was and was not removed, and never
calls a partial erasure complete.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from src.domain.erasure.models import ErasureReport, Group, GroupCount, Level
from src.ui import theme
from src.ui.dialogs.base import DialogWindow
from src.ui.widgets.buttons import Button
from src.ui.widgets.surface import bottom_rule
from src.ui.widgets.typography import body

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


class EraseDialog(DialogWindow):
    confirmed = Signal()
    retryRequested = Signal()

    def __init__(
        self,
        level: Level,
        counts: Sequence[GroupCount],
        character_name: str | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Erase", parent=parent)
        self._level = level
        self._name = character_name or "the character"
        self._show_counts(counts)

    def _show_counts(self, counts: Sequence[GroupCount]) -> None:
        shown = [c for c in counts if c.rows > 0]
        total = sum(c.rows for c in shown)
        everything = self._level is Level.EVERYTHING
        self.title("Erase everything?" if everything else "Erase memory?")
        if everything:
            self.text(f"Everything goes, without exception — {self._name} too.")
        else:
            self.text(
                "Everything remembered goes, what I hold about myself included. "
                f"{self._name[0].upper()}{self._name[1:]} and your settings stay."
            )
        if not shown:
            self.text("There is nothing to erase.")
            self.add_button(Button("Close"), self.close)
            return
        self.content.addSpacing(10)
        for count in shown:
            self.content.addWidget(_group_row(count))
        self.content.addSpacing(12)
        self.text("This cannot be undone.", colour=theme.DANGER)
        self.buttons.addStretch(1)
        self.add_button(Button("Cancel"), self.close)
        noun = "item" if total == 1 else "items"
        self.erase = self.add_button(
            Button(f"Erase {total} {noun}", variant="danger"), self.confirmed.emit
        )

    def showWorking(self) -> None:
        self.clear()
        self.title("Erasing…")
        self.text("This can take a moment while the file is rewritten.")

    def showReport(self, report: ErasureReport) -> None:
        """What is gone, and what is not. A partial erasure offers to run again."""
        self.clear()
        if report.complete:
            self.title("Erased")
            self.text("Nothing of it remains on the disk.")
            self.buttons.addStretch(1)
            self.add_button(Button("Close", variant="primary"), self.close)
            return
        self.title("Not everything was erased")
        if report.erased:
            self.text("Removed: " + _names(report.erased) + ".")
        if report.failed:
            self.text("Not removed: " + _names(report.failed) + ".")
        if not report.compacted:
            self.text(
                "The data file could not be rewritten, so removed rows may still "
                "be in it."
            )
        self._offer_retry()

    def showStopped(self) -> None:
        """The erasure ended with no report, so nobody knows which groups went.
        Running it again erases whatever is left."""
        self.clear()
        self.title("Not everything was erased")
        self.text("Erasing stopped partway, so some of it may still be on the disk.")
        self._offer_retry()

    def _offer_retry(self) -> None:
        self.buttons.addStretch(1)
        self.add_button(Button("Close"), self.close)
        self.retry = self.add_button(
            Button("Try again", variant="primary"), self.retryRequested.emit
        )


def _group_row(count: GroupCount) -> QWidget:
    widget = bottom_rule()
    row = QHBoxLayout(widget)
    row.setContentsMargins(2, 8, 2, 8)
    row.addWidget(body(GROUP_NAMES[count.group]))
    row.addStretch(1)
    if count.group is not Group.SETTINGS:
        row.addWidget(body(f"{count.rows:,}", colour=theme.TEXT_SECONDARY))
    return widget


def _names(groups: Sequence[Group]) -> str:
    return ", ".join(GROUP_NAMES[group].lower() for group in groups)
