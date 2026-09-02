"""Starting Cognia.

Creates the QApplication, registers the vendored fonts, applies the style
sheet, and wires the three surfaces to each other. This is the only module that
knows about all three.

It is also the only module that knows about all three *layers*. The views below
it render domain models and report what the user did; the adapters beside it
keep conversations on disk and ask a model on this machine for a reply; neither
imports the other. The joins are all here.

Still no observation: nothing reads the operating system, and the companion on
the desktop watches nothing. What the user says is kept because they said it.
"""

from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import QObject, QPoint, QThread, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import src.app.local_only  # noqa: F401  - must precede any LangChain import
from src.app import config
from src.app.chat_worker import ChatWorker
from src.core.models import COMPANION, USER, Message
from src.infrastructure.ai.ollama_agent import OllamaAgent
from src.infrastructure.storage.sqlite_store import (
    UNTITLED,
    SqliteConversationStore,
    title_from,
)
from src.ui import fonts, icons, theme
from src.ui.dialogs.tray_menu import TrayMenu
from src.ui.views import sample_data
from src.ui.windows.companion_window import CompanionWindow
from src.ui.windows.main_window import MainWindow
from src.utils import paths

_PAUSE_LABELS = {option.id: option.paused_label for option in sample_data.PAUSE_OPTIONS}

DATABASE = "cognia.sqlite3"


class Cognia(QObject):
    """Holds the windows, the store, and the thread the model answers on."""

    #: Emitted on the GUI thread, delivered on the worker's. Qt queues it,
    #: which is the whole reason the window keeps painting while a 2B model
    #: takes its time.
    askModel = Signal(str, object)

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.companion_hidden = False

        self.window = MainWindow()
        self.companion = CompanionWindow()
        self.menu = TrayMenu()

        self.tray = QSystemTrayIcon(icons.icon("chat-circle", 32, theme.ACCENT))
        self.tray.setToolTip("Cognia")

        # The character is still mockup copy; FR-02 will give it an owner.
        self.character = sample_data.CHARACTERS[0]
        self.prompt = config.system_prompt(self.character.name, self.character.role)

        self.store = SqliteConversationStore(paths.data_file(DATABASE))
        self.conversation = self.store.latest() or self.store.create(
            self.character.id, datetime.now()
        )

        self.thread = QThread()
        self.thread.setObjectName("cognia-model")
        self.worker = ChatWorker(
            OllamaAgent(config.OLLAMA_MODEL, config.OLLAMA_BASE_URL)
        )
        self.worker.moveToThread(self.thread)
        self.thread.start()

        self._wire()

    def _wire(self) -> None:
        self.window.pauseMenuRequested.connect(self._open_menu)
        self.window.hideCompanionRequested.connect(self._toggle_companion)
        self.window.nudgeRequested.connect(self._show_nudge)
        self.window.resumed.connect(self._resume)

        self.window.messageSent.connect(self._say)
        self.window.conversationChosen.connect(self._open_conversation)
        self.window.newConversationRequested.connect(self._new_conversation)

        self.askModel.connect(self.worker.request)
        self.worker.chunk.connect(self.window.chat.appendChunk)
        self.worker.finished.connect(self._replied)
        self.worker.failed.connect(self.window.chat.showError)

        self.menu.paused.connect(self._pause)
        self.menu.hideCompanionRequested.connect(self._toggle_companion)

        self.tray.activated.connect(self._tray_activated)
        self.app.aboutToQuit.connect(self._shutdown)

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

    # ── the conversation ──────────────────────────────────────────────────

    def _say(self, text: str) -> None:
        """The user has said something. Record it, show it, then ask."""
        message = self.store.append(
            Message.new(self.conversation.id, USER, text, datetime.now())
        )
        if self.conversation.title == UNTITLED:
            self.store.retitle(self.conversation.id, title_from(text))
            self.conversation = self._reread(self.conversation.id)

        self.window.chat.appendMessage(message)
        self.window.chat.beginReply()
        self._refresh_picker()

        history = self.store.history(self.conversation.id, config.HISTORY_MESSAGES)
        self.askModel.emit(self.prompt, history)

    def _replied(self, text: str) -> None:
        """A reply arrived whole. It is recorded only now, never mid-stream."""
        self.store.append(
            Message.new(self.conversation.id, COMPANION, text, datetime.now())
        )
        self.window.chat.endReply(text)
        self._refresh_picker()

    def _new_conversation(self) -> None:
        if not self.store.history(self.conversation.id, 1):
            return  # already sitting in an empty one; don't pile up more
        self.conversation = self.store.create(self.character.id, datetime.now())
        self.window.chat.loadConversation([])
        self._refresh_picker()

    def _open_conversation(self, conversation_id: str) -> None:
        if conversation_id == self.conversation.id:
            return
        self.conversation = self._reread(conversation_id)
        self.window.chat.loadConversation(self.store.history(conversation_id))
        self._refresh_picker()

    def _reread(self, conversation_id: str):
        found = next(
            (c for c in self.store.conversations() if c.id == conversation_id), None
        )
        return found or self.conversation

    def _refresh_picker(self) -> None:
        self.window.chat.setConversations(
            self.store.conversations(), self.conversation.id
        )

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

    # ── start and stop ────────────────────────────────────────────────────

    def start(self) -> None:
        self.window.chat.loadConversation(self.store.history(self.conversation.id))
        self._refresh_picker()

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

    def _shutdown(self) -> None:
        """A reply in flight is abandoned and not written down (UC-09 E2)."""
        self.worker.cancel()
        self.thread.quit()
        self.thread.wait(5000)
        self.store.close()


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

    config.load()
    fonts.load()
    app.setFont(theme.font(15))
    app.setPalette(_palette())
    app.setStyleSheet(theme.stylesheet())

    cognia = Cognia(app)
    cognia.start()
    return app.exec()
