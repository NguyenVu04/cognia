"""The tray menu: open the window, pause or resume, show or hide the companion,
and quit. Every one of these is also in the main window."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMenu, QWidget

from src.ui import icons, theme

HOUR = "hour"
TODAY = "today"
UNTIL_ON = "off"
PAUSE_OPTIONS = (
    (HOUR, "For one hour", "clock"),
    (TODAY, "Until the end of today", "moon"),
    (UNTIL_ON, "Until I switch it back on", "power"),
)


class TrayMenu(QMenu):
    openRequested = Signal()
    #: How long: ``hour``, ``today`` or ``off``.
    pauseRequested = Signal(str)
    resumeRequested = Signal()
    companionToggled = Signal()
    quitRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(theme.font(13.5))
        self.open_action = self.addAction("Open Cognia")
        self.open_action.triggered.connect(self.openRequested)
        self.addSeparator()
        self.pause_menu = self.addMenu(icons.icon("pause", 16, theme.TEXT), "Pause")
        self.pause_menu.setFont(theme.font(13.5))
        for option, text, icon_name in PAUSE_OPTIONS:
            action = self.pause_menu.addAction(
                icons.icon(icon_name, 16, theme.TEXT), text
            )
            action.triggered.connect(
                lambda _=False, o=option: self.pauseRequested.emit(o)
            )
        self.resume_action = self.addAction(
            icons.icon("play", 16, theme.TEXT), "Resume"
        )
        self.resume_action.triggered.connect(self.resumeRequested)
        self.companion_action = self.addAction("Hide companion")
        self.companion_action.triggered.connect(self.companionToggled)
        self.addSeparator()
        quit_action = self.addAction(icons.icon("power", 16, theme.TEXT), "Quit Cognia")
        quit_action.triggered.connect(self.quitRequested)
        self.setPaused(False)

    def setPaused(self, paused: bool) -> None:
        self.pause_menu.menuAction().setVisible(not paused)
        self.resume_action.setVisible(paused)
        self.companion_action.setEnabled(not paused)

    def setCompanionHidden(self, hidden: bool, name: str) -> None:
        who = name or "companion"
        self.companion_action.setText(f"Show {who}" if hidden else f"Hide {who}")
