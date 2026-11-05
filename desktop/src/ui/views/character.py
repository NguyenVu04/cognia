"""Character, and changing it later.

The character in force, read-only because the four ship as they are, and every
earlier version kept beside it, because a change is not always an improvement.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from src.domain.character.models import Version
from src.ui import theme
from src.ui.widgets.buttons import dashed_button, small_button
from src.ui.widgets.hatch import HatchPanel
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import Panel, bottom_rule
from src.ui.widgets.typography import (
    body,
    heading,
    kicker,
    label,
    lede,
    paragraph,
)

DESCRIPTION_WIDTH = 472

_ENGLISH = QLocale(QLocale.Language.English)
_ORIGIN = {"chosen": "chosen", "restored": "restored", "proposal": "approved change"}


def _day(moment: datetime) -> str:
    return _ENGLISH.toString(moment.astimezone().date(), "d MMM")


class CharacterView(QWidget):
    firstRunRequested = Signal()
    #: The id of the version to put back in force.
    restoreRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.pane = ScrollPane(padding=(34, 40, 40, 40))
        layout.addWidget(self.pane)
        column = self.pane.column

        column.addWidget(heading("Character"))
        column.addSpacing(4)
        column.addWidget(
            lede(
                "In force from the next message. Every earlier version is "
                "kept, appearance included — a change is not always an "
                "improvement.",
                max_width=600,
            )
        )
        column.addSpacing(26)

        split = QHBoxLayout()
        split.setSpacing(26)
        split.addWidget(self._appearance(), 0, Qt.AlignmentFlag.AlignTop)
        split.addWidget(self._details(), 1)
        holder = QWidget()
        holder.setFixedWidth(716)  # max-width: 920px, capped by the column
        holder.setLayout(split)
        column.addWidget(holder, 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)

    # ── what the application tells it to show ─────────────────────────────

    def setCharacter(  # noqa: N802 - matches Qt naming
        self,
        current: Version,
        earlier: Sequence[tuple[Version, datetime]],
    ) -> None:
        """The version in force, and each earlier version with the moment it
        stopped being in force, newest first."""
        self.name.setText(current.name)
        self.role.setText(current.role)
        self._show_description(current.description)
        self._clear_versions()
        self.history_error.setVisible(False)
        self.none_earlier.setVisible(not earlier)
        for version, until in earlier:
            self.versions.addWidget(self._version_row(version, until))
        self.pane.refresh()

    def showHistoryError(self, text: str) -> None:  # noqa: N802 - Qt naming
        """The earlier versions cannot be read: say so, never an empty list."""
        self._clear_versions()
        self.none_earlier.setVisible(False)
        self.history_error.setText(text)
        self.history_error.setVisible(True)

    # ── building ──────────────────────────────────────────────────────────

    def _appearance(self) -> Panel:
        card = Panel(
            fill=theme.BG_CARD, ring=theme.BORDER_SUBTLE, radius=10,
            padding=(14, 14, 14, 14),
        )
        card.setFixedWidth(200)
        sprite = HatchPanel("appearance\nplaceholder", radius=7)
        sprite.setFixedHeight(180)
        card.body().addWidget(sprite)
        card.body().addSpacing(12)
        self.name = label("", font=theme.font(15, 500), colour=theme.TEXT)
        card.body().addWidget(self.name)
        self.role = label("", font=theme.font(12.5), colour=theme.muted(0.5))
        card.body().addWidget(self.role)
        return card

    def _details(self) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        column.addWidget(body("The character", px=13, weight=500))
        column.addSpacing(8)
        self.description = QVBoxLayout()
        self.description.setContentsMargins(0, 0, 0, 0)
        self.description.setSpacing(6)
        column.addLayout(self.description)
        column.addSpacing(12)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        open_first_run = dashed_button(
            "Choose another character", px=13.5, radius=8, padding=(10, 16)
        )
        open_first_run.clicked.connect(self.firstRunRequested)
        actions.addWidget(open_first_run)
        actions.addStretch(1)
        column.addLayout(actions)

        column.addSpacing(26)
        column.addWidget(kicker("Earlier versions"))
        column.addSpacing(10)
        self.versions = QVBoxLayout()
        self.versions.setContentsMargins(0, 0, 0, 0)
        self.versions.setSpacing(0)
        column.addLayout(self.versions)
        self.none_earlier = body("None yet.", px=13, alpha=0.5)
        column.addWidget(self.none_earlier)
        self.history_error = label("", font=theme.font(13), colour=theme.muted(0.7))
        self.history_error.setVisible(False)
        column.addWidget(self.history_error)
        return holder

    def _show_description(self, text: str) -> None:
        """One paragraph for each line, so the examples keep their lines."""
        while self.description.count():
            widget = self.description.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for line in text.strip().splitlines():
            if line.strip():
                self.description.addWidget(
                    paragraph(
                        line.strip(), font=theme.font(13.5),
                        colour=theme.muted(0.72), max_width=DESCRIPTION_WIDTH,
                    )
                )

    def _clear_versions(self) -> None:
        while self.versions.count():
            widget = self.versions.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def _version_row(self, version: Version, until: datetime) -> QWidget:
        widget = bottom_rule()
        row = QHBoxLayout(widget)
        row.setContentsMargins(2, 11, 2, 11)
        row.setSpacing(14)
        origin = _ORIGIN.get(version.origin, version.origin)
        row.addWidget(body(f"{version.name} · {origin}", px=13.5, alpha=0.8))
        row.addStretch(1)
        row.addWidget(
            body(f"{_day(version.created_at)} – {_day(until)}", px=12, alpha=0.42)
        )
        restore = small_button("Restore", padding=(5, 10))
        restore.clicked.connect(lambda: self.restoreRequested.emit(version.id))
        row.addWidget(restore)
        return widget
