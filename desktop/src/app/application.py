"""Starting Cognia.

Creates the QApplication, registers the vendored fonts, applies the style
sheet, and wires the three surfaces to each other. This is the only module
that knows about all three.

No domain, no storage, no observation: this build is the design made runnable,
and every response below changes what is on screen and nothing else.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPoint
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from src.ui import fonts, icons, theme
from src.ui.dialogs.tray_menu import TrayMenu
from src.ui.views import sample_data
from src.ui.windows.companion_window import CompanionWindow
from src.ui.windows.main_window import MainWindow

_PAUSE_LABELS = {option.id: option.paused_label for option in sample_data.PAUSE_OPTIONS}


class Cognia:
    """Holds the windows and the little presentational state they share."""

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.companion_hidden = False

        self.window = MainWindow()
        self.companion = CompanionWindow()
        self.menu = TrayMenu()

        self.tray = QSystemTrayIcon(icons.icon("chat-circle", 32, theme.ACCENT))
        self.tray.setToolTip("Cognia")

        self._wire()

    def _wire(self) -> None:
        self.window.pauseMenuRequested.connect(self._open_menu)
        self.window.hideCompanionRequested.connect(self._toggle_companion)
        self.window.nudgeRequested.connect(self._show_nudge)
        self.window.resumed.connect(self._resume)

        self.menu.paused.connect(self._pause)
        self.menu.hideCompanionRequested.connect(self._toggle_companion)

        self.tray.activated.connect(self._tray_activated)

    # ── tray ──────────────────────────────────────────────────────────────

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.Context,
        ):
            self._open_menu()

    def _open_menu(self) -> None:
        if self.menu.isVisible():
            self.menu.hide()
            return
        geometry = self.tray.geometry()
        if geometry.isNull():
            # No usable tray rectangle: fall back to the corner of the screen.
            available = self.window.screen().availableGeometry()
            anchor = QPoint(available.right() - 18, available.bottom() - 10)
        else:
            anchor = QPoint(geometry.right(), geometry.top() - 10)
        self.menu.popup_at(anchor)

    # ── responses ─────────────────────────────────────────────────────────

    def _pause(self, option_id: str) -> None:
        self.window.showPaused(_PAUSE_LABELS[option_id])
        self.companion.hide()

    def _resume(self) -> None:
        self.window.hidePaused()
        if not self.companion_hidden:
            self.companion.show()

    def _toggle_companion(self) -> None:
        self.companion_hidden = not self.companion_hidden
        self.companion.setVisible(not self.companion_hidden)
        label = "Show on desktop" if self.companion_hidden else "Hide from desktop"
        self.window.setHideLabel(label)
        self.menu.setHideLabel(label)

    def _show_nudge(self) -> None:
        self.companion_hidden = False
        self.window.setHideLabel("Hide from desktop")
        self.menu.setHideLabel("Hide from desktop")
        self.companion.show()
        self.companion.showNudge()

    # ── start ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self.window.centre_on_screen()
        self.window.show()

        # Bottom right, kept wholly on screen. The window is larger than the
        # sprite by the transparent gutter its nudge shadow is painted into,
        # so the offset is measured from the sprite, not the window.
        available = self.window.screen().availableGeometry()
        gutter = self.companion.margin
        self.companion.move(
            available.right() - self.companion.width() + gutter - 24,
            available.bottom() - self.companion.height() + gutter - 24,
        )
        self.companion.show()
        self.tray.show()


def _palette() -> QPalette:
    """Placeholder text is a palette role in Qt, not a style-sheet property."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.PlaceholderText, theme.muted(0.38))
    palette.setColor(QPalette.ColorRole.Text, theme.TEXT)
    palette.setColor(QPalette.ColorRole.WindowText, theme.TEXT)
    return palette


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Cognia")
    app.setQuitOnLastWindowClosed(True)

    fonts.load()
    app.setFont(theme.font(15))
    app.setPalette(_palette())
    app.setStyleSheet(theme.stylesheet())

    cognia = Cognia(app)
    cognia.start()
    return app.exec()
