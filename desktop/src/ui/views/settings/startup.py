"""Starting with Windows."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from src.ui.views.settings.common import Section, setting_row
from src.ui.widgets.toggle import PillToggle


class StartupSection(Section):
    startWithWindowsToggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Startup",
            "When you close the window I'll stay nearby in the tray. Choose Quit "
            "there to say goodbye.",
            parent,
        )
        panel = self.card()
        self.toggle = PillToggle("large", checked=False)
        self.toggle.clicked.connect(
            lambda: self.startWithWindowsToggled.emit(self.toggle.isChecked())
        )
        panel.body().addWidget(setting_row(
            "Start with Windows", "I'll be there quietly when you sign in.",
            self.toggle)[0])

    def setStartWithWindows(self, on: bool) -> None:
        self.toggle.setChecked(on)
