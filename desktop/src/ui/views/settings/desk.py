"""Desk awareness: on or off, today's time at the machine, and the
applications that are not counted."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import Signal, SignalInstance
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from src.ui import formatting, theme
from src.ui.views.settings.common import Section, setting_row
from src.ui.widgets.buttons import Button
from src.ui.widgets.layout import clear
from src.ui.widgets.toggle import PillToggle
from src.ui.widgets.typography import body, caption, kicker

READS = (
    "I only notice whether you're around, whether the screen is locked or "
    "you're presenting, and which app is open. Never what you type or what's "
    "on your screen."
)


class DeskSection(Section):
    awarenessToggled = Signal(bool)
    excludeRequested = Signal(str)
    includeRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Desk awareness",
            "This lets me know when you're at your desk, so I can wait while "
            "you're busy and say hello when you're back. Everything else works "
            "without it.",
            parent,
        )
        top = self.card()
        self.toggle = PillToggle("large", checked=False)
        # Only a click by the user asks for a change; setAwareness does not.
        self.toggle.clicked.connect(
            lambda: self.awarenessToggled.emit(self.toggle.isChecked())
        )
        top.body().addWidget(setting_row("Desk awareness", READS, self.toggle)[0])

        self.today = self.card()
        self.today.body().addWidget(kicker("Today"))
        self.today.body().addSpacing(6)
        self.desk_time = body("")
        self.today.body().addWidget(self.desk_time)
        self.today.body().addSpacing(8)
        self.apps = QVBoxLayout()
        self.apps.setSpacing(4)
        self.today.body().addLayout(self.apps)

        excluded = self.card()
        excluded.body().addWidget(kicker("Not counted"))
        excluded.body().addSpacing(6)
        self.excluded = QVBoxLayout()
        self.excluded.setSpacing(4)
        excluded.body().addLayout(self.excluded)
        excluded.body().addSpacing(6)
        add = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Application name, such as Steam.exe")
        self.name.setFont(theme.font(13.5))
        self.name.returnPressed.connect(self._exclude_typed)
        add.addWidget(self.name, 1)
        exclude = Button("Exclude", size="small")
        exclude.clicked.connect(self._exclude_typed)
        add.addWidget(exclude)
        excluded.body().addLayout(add)
        excluded.body().addSpacing(4)
        excluded.body().addWidget(caption(
            "I'll forget the time spent in it and stop keeping track. You still "
            "count as being at your desk while you use it."))
        self.setAwareness(False)
        self.setExcluded(())

    def setAwareness(self, on: bool) -> None:
        """Show whether desk awareness is on, as the core recorded it."""
        self.toggle.setChecked(on)
        self.today.setVisible(on)

    def setToday(self, desk_text: str, minutes: Mapping[str, int]) -> None:
        """Today's time at the machine, and the minutes in each application."""
        self.desk_time.setText(desk_text)
        clear(self.apps)
        ranked = sorted(minutes.items(), key=lambda kv: -kv[1])
        if not ranked:
            self.apps.addWidget(caption("No application time recorded today.", px=13))
        for name, count in ranked:
            self.apps.addWidget(_app_row(
                name, formatting.duration(count), "Exclude", self.excludeRequested
            ))

    def setExcluded(self, names: Sequence[str]) -> None:
        clear(self.excluded)
        if not names:
            self.excluded.addWidget(caption("Every application is counted.", px=13))
        for name in names:
            self.excluded.addWidget(
                _app_row(name, "", "Count again", self.includeRequested)
            )

    def _exclude_typed(self) -> None:
        name = self.name.text().strip()
        if name:
            self.name.clear()
            self.excludeRequested.emit(name)


def _app_row(name: str, detail: str, action: str, signal: SignalInstance) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(body(name))
    layout.addStretch(1)
    if detail:
        layout.addWidget(body(detail, colour=theme.TEXT_SECONDARY))
    button = Button(action, size="small", variant="ghost")
    button.clicked.connect(lambda: signal.emit(name))
    layout.addWidget(button)
    return row
