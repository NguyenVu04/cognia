"""Character, and changing it later.

The character in force, read-only because the four ship as they are, and every
earlier version kept beside it, because a change is not always an improvement.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.domain.character.models import Version
from src.ui import formatting, theme
from src.ui.widgets.buttons import Button
from src.ui.widgets.layout import clear
from src.ui.widgets.portrait import portrait
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import bottom_rule, card
from src.ui.widgets.typography import (
    body,
    caption,
    heading,
    kicker,
    label,
    lede,
    paragraph,
)

DESCRIPTION_WIDTH = 440
PORTRAIT = QSize(196, 236)
_ORIGIN = {"chosen": "chosen", "restored": "restored", "proposal": "approved change"}


def _day(moment: datetime) -> str:
    return formatting.short_date(formatting.local_day(moment))


class CharacterView(QWidget):
    firstRunRequested = Signal()
    #: The id of the version to put back in force.
    restoreRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pane = ScrollPane(padding=(30, 36, 36, 36))
        layout.addWidget(self.pane)
        column = self.pane.column
        column.addWidget(heading("Character"))
        column.addSpacing(6)
        column.addWidget(lede(
            "A new choice starts with your next message, and you can always go "
            "back."
        ))
        column.addSpacing(22)
        split = QHBoxLayout()
        split.setSpacing(26)
        split.addWidget(self._appearance(), 0, Qt.AlignmentFlag.AlignTop)
        split.addLayout(self._details(), 1)
        column.addLayout(split)
        column.addStretch(1)

    def setCharacter(
        self,
        current: Version,
        earlier: Sequence[tuple[Version, datetime]],
    ) -> None:
        """The version in force, and each earlier version with the moment it
        stopped being in force, newest first."""
        self.name.setText(current.name)
        self.role.setText(current.role)
        pixmap = portrait(current.appearance_id, PORTRAIT)
        self.picture.setPixmap(pixmap) if pixmap is not None else self.picture.clear()
        clear(self.description)
        for line in current.description.strip().splitlines():
            if line.strip():
                self.description.addWidget(paragraph(
                    line.strip(), font=theme.font(14), colour=theme.TEXT_SECONDARY,
                    max_width=DESCRIPTION_WIDTH,
                ))
        clear(self.versions)
        self.history_error.setVisible(False)
        self.none_earlier.setVisible(not earlier)
        for version, until in earlier:
            self.versions.addWidget(self._version_row(version, until))
        self.pane.refresh()

    def showHistoryError(self, text: str) -> None:
        """The earlier versions cannot be read: say so, never an empty list."""
        clear(self.versions)
        self.none_earlier.setVisible(False)
        self.history_error.setText(text)
        self.history_error.setVisible(True)

    def _appearance(self) -> QWidget:
        panel = card(padding=(12, 12, 14, 12), radius=14)
        panel.setFixedWidth(PORTRAIT.width() + 24)
        self.picture = QLabel()
        self.picture.setFixedSize(PORTRAIT)
        self.picture.setStyleSheet(
            f"background: {theme.css(theme.BG_INSET)}; border-radius: 10px;"
        )
        panel.body().addWidget(self.picture)
        panel.body().addSpacing(10)
        self.name = label("", font=theme.font(18, 800))
        panel.body().addWidget(self.name)
        self.role = caption("", px=13)
        panel.body().addWidget(self.role)
        return panel

    def _details(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(0)
        column.addWidget(kicker("Who they are"))
        column.addSpacing(8)
        self.description = QVBoxLayout()
        self.description.setSpacing(6)
        column.addLayout(self.description)
        column.addSpacing(14)
        change = Button("Choose another character", icon_name="user-focus")
        change.clicked.connect(self.firstRunRequested)
        column.addWidget(change, 0, Qt.AlignmentFlag.AlignLeft)
        column.addSpacing(26)
        column.addWidget(kicker("Earlier versions"))
        column.addSpacing(8)
        self.versions = QVBoxLayout()
        self.versions.setSpacing(0)
        column.addLayout(self.versions)
        self.none_earlier = caption("None yet.", px=13)
        column.addWidget(self.none_earlier)
        self.history_error = body("", colour=theme.DANGER, wrap=True)
        self.history_error.setVisible(False)
        column.addWidget(self.history_error)
        column.addStretch(1)
        return column

    def _version_row(self, version: Version, until: datetime) -> QWidget:
        widget = bottom_rule()
        row = QHBoxLayout(widget)
        row.setContentsMargins(2, 9, 2, 9)
        row.setSpacing(12)
        origin = _ORIGIN.get(version.origin, version.origin)
        row.addWidget(body(f"{version.name} · {origin}"))
        row.addStretch(1)
        row.addWidget(caption(f"{_day(version.created_at)} – {_day(until)}"))
        restore = Button("Restore", size="small", icon_name="arrow-counter-clockwise")
        restore.clicked.connect(lambda: self.restoreRequested.emit(version.id))
        row.addWidget(restore)
        return widget
