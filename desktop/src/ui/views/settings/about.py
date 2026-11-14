"""About: which Cognia this is, and its error log."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from src.ui import theme
from src.ui.views.settings.common import Section, setting_row
from src.ui.widgets.buttons import Button
from src.ui.widgets.typography import label


class AboutSection(Section):
    logRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "About",
            "Which Cognia this is, and the log I keep when something goes wrong.",
            parent,
        )
        version = self.card()
        self.version = label("", font=theme.font(14.5, 700))
        version.body().addWidget(
            setting_row(
                "Version",
                "Say this number when you report a problem.",
                self.version,
            )[0]
        )

        log = self.card()
        self.open_log = Button("Open the log", size="small")
        self.open_log.clicked.connect(self.logRequested)
        log.body().addWidget(
            setting_row(
                "Error log",
                "It stays on this computer and is never sent anywhere. It can "
                "hold words from our conversations, so erasing memory erases it "
                "too.",
                self.open_log,
            )[0]
        )

    def setVersion(self, text: str) -> None:
        self.version.setText(text)
