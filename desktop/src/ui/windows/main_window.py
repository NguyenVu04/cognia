"""The main window.

Three top-level states: the choice of a character, the two onboarding steps
after it, and the application — the sidebar plus one of four screens.
Closing hides the window; Cognia keeps running in the tray.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QWidget

from src.ui.views.character import CharacterView
from src.ui.views.chat import ChatView
from src.ui.views.first_run import FirstRunView
from src.ui.views.memory import MemoryView
from src.ui.views.navigation import (
    CHARACTER,
    COMPANION,
    MEMORY,
    NAV_ITEMS,
    SETTINGS,
)
from src.ui.views.onboarding import DeskStep, TipsStep
from src.ui.views.settings.view import SettingsView
from src.ui.widgets.frameless import FramelessWindow
from src.ui.widgets.paused_overlay import PausedOverlay
from src.ui.widgets.sidebar import Sidebar
from src.ui.widgets.speech_bubble import SpeechBubble
from src.ui.widgets.spinner import Spinner
from src.ui.widgets.titlebar import HEIGHT as TITLEBAR_HEIGHT
from src.ui.widgets.titlebar import TitleBar

WIDTH = 1040
HEIGHT = 720

_NEED_A_CHARACTER = (COMPANION, CHARACTER)


class MainWindow(FramelessWindow):
    #: The close button was pressed; the window should hide, not quit.
    closeRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cognia")
        self.resize_body(WIDTH, HEIGHT)
        frame = self.body.body()

        self.titlebar = TitleBar()
        self.titlebar.minimiseRequested.connect(self.showMinimized)
        self.titlebar.closeRequested.connect(self.closeRequested)
        frame.addWidget(self.titlebar)

        self.stack = QStackedWidget()
        frame.addWidget(self.stack, 1)
        self._needs_character = False
        self._quitting = False
        self.stack.addWidget(self._application_page())
        self.first_run = FirstRunView()
        self.first_run.backRequested.connect(lambda: self.showApplication(CHARACTER))
        self.stack.addWidget(self.first_run)
        self.desk_step = DeskStep()
        self.stack.addWidget(self.desk_step)
        self.tips_step = TipsStep()
        self.tips_step.done.connect(lambda: self.showApplication(COMPANION))
        self.stack.addWidget(self.tips_step)

        self.overlay = PausedOverlay(self.body)
        self.overlay.hide()
        self.loading = Spinner(self.body)
        self.loading.hide()
        # A message held while the companion was hidden is said here.
        self.bubble = SpeechBubble(self.body)
        self.bubble.closed.connect(self.bubble.hide)
        self.bubble.hide()

        self._shortcuts()
        self.go(COMPANION)

    def _application_page(self) -> QWidget:
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.sidebar = Sidebar()
        self.sidebar.navigated.connect(self.go)
        row.addWidget(self.sidebar)

        self.screens = QStackedWidget()
        self.chat = ChatView()
        self.memory = MemoryView()
        self.character = CharacterView()
        self.settings = SettingsView()
        self._by_id: dict[str, QWidget] = {
            COMPANION: self.chat,
            MEMORY: self.memory,
            CHARACTER: self.character,
            SETTINGS: self.settings,
        }
        for screen in self._by_id.values():
            self.screens.addWidget(screen)
        row.addWidget(self.screens, 1)
        return page

    def _shortcuts(self) -> None:
        for item in NAV_ITEMS:
            QShortcut(QKeySequence(item.shortcut), self).activated.connect(
                lambda i=item.id: self._shortcut_go(i)
            )
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(
            self.chat.newConversationRequested
        )
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._find)

    def _shortcut_go(self, screen_id: str) -> None:
        if self.stack.currentIndex() == 0:
            self.go(screen_id)

    def _find(self) -> None:
        if self.stack.currentIndex() == 0:
            self.go(MEMORY)
            self.memory.focusSearch()

    # ── navigation ────────────────────────────────────────────────────────

    def go(self, screen_id: str) -> None:
        """Show a screen. With no character in force, the screens that need one
        lead to the choice of a character instead."""
        if self._needs_character and screen_id in _NEED_A_CHARACTER:
            self.showFirstRun()
            return
        self.screens.setCurrentWidget(self._by_id[screen_id])
        self.sidebar.setCurrent(screen_id)

    def current(self) -> str:
        return self.sidebar.current()

    def openSettings(self, section: str) -> None:
        self.showApplication(SETTINGS)
        self.settings.openSection(section)

    def showFirstRun(self) -> None:
        self.stack.setCurrentWidget(self.first_run)

    def showOnboarding(self) -> None:
        self.stack.setCurrentWidget(self.desk_step)

    def showTips(self) -> None:
        self.stack.setCurrentWidget(self.tips_step)

    def showApplication(self, screen_id: str = COMPANION) -> None:
        self.stack.setCurrentIndex(0)
        self.go(screen_id)

    def setNeedsCharacter(self, needed: bool) -> None:
        self._needs_character = needed

    def setLoading(self, loading: bool) -> None:
        """Turn a spinner in the middle of the window while the data loads."""
        if loading:
            self._place(self.loading)
            self.loading.show()
            self.loading.raise_()
        else:
            self.loading.hide()

    # ── paused state ──────────────────────────────────────────────────────

    def showPaused(self, until_text: str) -> None:
        self.overlay.setPause(until_text)
        self._place_overlay()
        self.overlay.show()
        self.overlay.raise_()

    def hidePaused(self) -> None:
        self.overlay.hide()

    def showHeldMessage(self, message) -> None:
        """Say a message that waited while the companion was hidden."""
        self.bubble.showMessage(message)
        self._place_bubble()
        self.bubble.show()
        self.bubble.raise_()

    # ── geometry ──────────────────────────────────────────────────────────

    def _place(self, widget: QWidget) -> None:
        below = TITLEBAR_HEIGHT
        widget.move(
            (self.body.width() - widget.width()) // 2,
            below + (self.body.height() - below - widget.height()) // 2,
        )

    def _place_overlay(self) -> None:
        self.overlay.setGeometry(
            0, TITLEBAR_HEIGHT, self.body.width(), self.body.height() - TITLEBAR_HEIGHT
        )

    def _place_bubble(self) -> None:
        self.bubble.adjustSize()
        self.bubble.move(
            self.body.width() - self.bubble.width() - 24,
            self.body.height() - self.bubble.height() - 96,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.overlay.isVisible():
            self._place_overlay()
        if self.loading.isVisible():
            self._place(self.loading)
        if self.bubble.isVisible():
            self._place_bubble()

    def allowClose(self) -> None:
        """Let the window close for real, when Cognia quits."""
        self._quitting = True

    def closeEvent(self, event) -> None:
        """Alt+F4 and the taskbar hide the window too; Quit is in the tray."""
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self.closeRequested.emit()

    def centre_on_screen(self) -> None:
        screen = self.screen().availableGeometry()
        self.move(screen.center() - self.rect().center())
