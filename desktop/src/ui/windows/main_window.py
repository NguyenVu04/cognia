"""The main window.

Frameless at 1010×748 with a 14px radius and the design's drop shadow. Two
top-level states — the first-run choice, which takes the whole window, and the
application, which is the sidebar plus one of six screens.

Qt does not clip children to a rounded parent, so the two widgets that reach a
corner with a colour of their own — the title bar and the sidebar — carry the
matching radius themselves.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QWidget

from src.ui import theme
from src.ui.views.character import CharacterView
from src.ui.views.chat import ChatView
from src.ui.views.desk import DeskView
from src.ui.views.first_run import FirstRunView
from src.ui.views.memory import MemoryView
from src.ui.views.proactivity import ProactivityView
from src.ui.views.sessions import SessionsView
from src.ui.widgets.paused_overlay import PausedOverlay
from src.ui.widgets.shadow import ShadowWindow
from src.ui.widgets.sidebar import Sidebar
from src.ui.widgets.titlebar import HEIGHT as TITLEBAR_HEIGHT
from src.ui.widgets.titlebar import TitleBar

WIDTH = 1010
HEIGHT = 748
RADIUS = 14


class MainWindow(ShadowWindow):
    pauseMenuRequested = Signal()
    hideCompanionRequested = Signal()
    nudgeRequested = Signal()
    resumed = Signal()
    messageSent = Signal(str)
    conversationChosen = Signal(str)
    newConversationRequested = Signal()

    def __init__(self) -> None:
        super().__init__(
            radius=RADIUS, fill=theme.BG_WINDOW, blur=70, dy=24, margin=48
        )
        self.setWindowTitle("Cognia")
        self.resize_body(WIDTH, HEIGHT)

        frame = self.body.body()
        frame.setSpacing(0)

        self.titlebar = TitleBar()
        self.titlebar.addRules(
            f"border-top-left-radius: {RADIUS}px;"
            f"border-top-right-radius: {RADIUS}px;"
        )
        self.titlebar.minimiseRequested.connect(self.showMinimized)
        self.titlebar.closeRequested.connect(self.close)
        frame.addWidget(self.titlebar)

        self.stack = QStackedWidget()
        frame.addWidget(self.stack, 1)

        self.first_run = FirstRunView()
        self.first_run.confirmed.connect(self.showApplication)
        self.stack.addWidget(self._application_page())
        self.stack.addWidget(self.first_run)
        self.stack.setCurrentIndex(0)

        self.overlay = PausedOverlay(self.body)
        self.overlay.resumed.connect(self.resumed)
        self.overlay.hide()

        self.go("chat")

    def _application_page(self) -> QWidget:
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.addRules(f"border-bottom-left-radius: {RADIUS}px;")
        self.sidebar.navigated.connect(self.go)
        self.sidebar.pauseRequested.connect(self.pauseMenuRequested)
        row.addWidget(self.sidebar)

        self.screens = QStackedWidget()
        self.chat = ChatView()
        self.chat.hideCompanionRequested.connect(self.hideCompanionRequested)
        self.chat.messageSent.connect(self.messageSent)
        self.chat.conversationChosen.connect(self.conversationChosen)
        self.chat.newConversationRequested.connect(self.newConversationRequested)
        self.sessions = SessionsView()
        self.sessions.nudgeRequested.connect(self.nudgeRequested)
        self.character = CharacterView()
        self.character.firstRunRequested.connect(self.showFirstRun)

        self._by_id: dict[str, QWidget] = {
            "chat": self.chat,
            "sessions": self.sessions,
            "memory": MemoryView(),
            "character": self.character,
            "desk": DeskView(),
            "proactivity": ProactivityView(),
        }
        for screen in self._by_id.values():
            self.screens.addWidget(screen)
        row.addWidget(self.screens, 1)
        return page

    # ── navigation ────────────────────────────────────────────────────────

    def go(self, screen_id: str) -> None:
        self.screens.setCurrentWidget(self._by_id[screen_id])
        self.sidebar.setCurrent(screen_id)

    def showFirstRun(self) -> None:
        self.stack.setCurrentWidget(self.first_run)

    def showApplication(self) -> None:
        self.stack.setCurrentIndex(0)
        self.go("chat")

    # ── paused state ──────────────────────────────────────────────────────

    def showPaused(self, label: str) -> None:
        self.overlay.setPauseLabel(label)
        self._place_overlay()
        self.overlay.show()
        self.overlay.raise_()

    def hidePaused(self) -> None:
        self.overlay.hide()

    def setHideLabel(self, text: str) -> None:
        self.chat.setHideLabel(text)

    def _place_overlay(self) -> None:
        """The overlay covers everything from below the title bar down."""
        self.overlay.setGeometry(
            0, TITLEBAR_HEIGHT, self.body.width(), self.body.height() - TITLEBAR_HEIGHT
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.overlay.isVisible():
            self._place_overlay()

    def centre_on_screen(self) -> None:
        screen = self.screen().availableGeometry()
        self.move(screen.center() - self.rect().center())
