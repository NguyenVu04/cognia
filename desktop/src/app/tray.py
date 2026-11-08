"""The tray icon and its menu, and pausing.

A pause stops reading the desk at once, on this thread, and then asks the core
to record it. The icon shows the paused state only after the core confirms;
if no confirmation comes within a second, the window says Cognia is still
running.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint, QTimer, Slot
from PySide6.QtWidgets import QSystemTrayIcon

from src.app.commands import Pause, Resume
from src.app.core.proactive import until_for
from src.ui import icons, theme
from src.ui.dialogs.tray_menu import TrayMenu

if TYPE_CHECKING:
    from src.app.application import Cognia

NOT_PAUSED = "Pausing didn't work, so I'm still running. Try again."
_CONFIRM_MS = 1000


class Tray(QObject):
    def __init__(self, cognia: Cognia) -> None:
        super().__init__()
        self.c = cognia
        self.paused = False
        self.menu = TrayMenu()
        self.icon = QSystemTrayIcon(icons.icon("chat-circle", 32, theme.ACCENT))
        self.icon.setToolTip("Cognia")
        self.icon.setContextMenu(self.menu)
        self._confirm = QTimer(self)
        self._confirm.setSingleShot(True)
        self._confirm.setInterval(_CONFIRM_MS)
        self._confirm.timeout.connect(self._not_confirmed)

        self.icon.activated.connect(self._activated)
        self.menu.openRequested.connect(cognia.show_window)
        self.menu.pauseRequested.connect(self.pause)
        self.menu.resumeRequested.connect(self.resume)
        self.menu.companionToggled.connect(lambda: cognia.companion_wiring.toggle())
        self.menu.quitRequested.connect(cognia.quit)
        window = cognia.window
        window.sidebar.pauseRequested.connect(self._pause_menu_at_sidebar)
        window.sidebar.resumeRequested.connect(self.resume)
        window.sidebar.companionToggled.connect(
            lambda: cognia.companion_wiring.toggle()
        )
        window.overlay.resumed.connect(self.resume)
        cognia.bridge.pauseChanged.connect(self._pause_changed)

    def show(self) -> None:
        self.icon.show()

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.c.show_window()

    def _pause_menu_at_sidebar(self) -> None:
        button = self.c.window.sidebar.pause
        self.menu.pause_menu.exec(
            button.mapToGlobal(QPoint(0, -self.menu.pause_menu.sizeHint().height()))
        )

    def pause(self, option: str) -> None:
        self.c.stop_sampler()
        self._confirm.start()
        self.c.bridge.send(Pause(until_for(option, self.c.now())))

    def resume(self) -> None:
        self.c.bridge.send(Resume())

    def _not_confirmed(self) -> None:
        self.c.window.chat.showNotice(NOT_PAUSED)
        self.c.awareness_changed(self.c.awareness_on)

    @Slot(bool, str, str)
    def _pause_changed(self, paused: bool, until: str, lasted: str) -> None:
        self._confirm.stop()
        was = self.paused
        self.paused = paused
        window = self.c.window
        self.menu.setPaused(paused)
        window.sidebar.setPaused(paused)
        name = "pause" if paused else "chat-circle"
        self.icon.setIcon(icons.icon(name, 32, theme.ACCENT))
        self.icon.setToolTip("Cognia — paused" if paused else "Cognia")
        if paused:
            window.showPaused(until)
            return
        window.hidePaused()
        self.c.awareness_changed(self.c.awareness_on)
        if was and lasted:
            window.chat.showNotice(f"Welcome back. I was paused for {lasted}.")

    def set_companion_label(self, hidden: bool, name: str) -> None:
        self.menu.setCompanionHidden(hidden, name)
