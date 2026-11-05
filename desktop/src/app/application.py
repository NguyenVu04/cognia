"""Starting Cognia.

Creates the QApplication, registers the vendored fonts, applies the style
sheet, and wires the three surfaces to each other. This is the only module that
knows about all three.

It also starts the two other threads. The core thread holds the data and every
decision; this thread only shows what the core sends and reports what the user
did. The model thread talks to the model servers. The views below render
domain models; the adapters beside them keep the data on disk and run the model
servers on this machine; neither imports the other. The joins are all here.

Still no observation: nothing reads the operating system, and the companion on
the desktop watches nothing. What the user says is kept because they said it,
and they see each line that is kept.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QPoint, Qt, QThread, Slot
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from src.app import config
from src.app.bridge import Bridge
from src.app.chat_worker import ChatWorker, Prepared
from src.app.commands import (
    ChooseCharacter,
    CorrectEntry,
    DeviceChosen,
    Erase,
    NewConversation,
    OfferCharacters,
    OpenConversation,
    PreviewErasure,
    RemoveEntry,
    ReplyArrived,
    ReplyLost,
    RestoreVersion,
    SendMessage,
    Stop,
    TurnPrepared,
    VectorsMade,
)
from src.app.core_host import CoreHost
from src.domain.erasure.models import Level
from src.domain.memory.models import Calibration
from src.infrastructure.ai.llama_client import LlamaClient
from src.infrastructure.ai.supervisor import ModelSupervisor
from src.ui import fonts, icons, theme
from src.ui.dialogs.erase_dialog import EraseDialog
from src.ui.dialogs.tray_menu import TrayMenu
from src.ui.views import sample_data
from src.ui.windows.companion_window import CompanionWindow
from src.ui.windows.main_window import MainWindow

_PAUSE_LABELS = {option.id: option.paused_label for option in sample_data.PAUSE_OPTIONS}
# How long the core may take to finish its last command when Cognia quits.
_CORE_STOP_SECONDS = 10


def _embedding_identity() -> str | None:
    """The embedding model as its file name and size, or ``None`` if missing."""
    path = config.model_path(config.EMBEDDING_MODEL)
    return f"{path.name}:{path.stat().st_size}" if path.is_file() else None


class Cognia(QObject):
    """Holds the windows, and starts the core thread and the model thread."""

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.companion_hidden = False
        self._erase_dialog: EraseDialog | None = None

        self.window = MainWindow()
        self.companion = CompanionWindow()
        self.menu = TrayMenu()

        self.tray = QSystemTrayIcon(icons.icon("chat-circle", 32, theme.ACCENT))
        self.tray.setToolTip("Cognia")

        self.bridge = Bridge()
        self.supervisor = ModelSupervisor(
            config.model_path(config.LLAMA_SERVER_VULKAN),
            config.model_path(config.LLAMA_SERVER_CPU),
            config.model_path(config.CHAT_MODEL),
            config.model_path(config.EMBEDDING_MODEL),
            context=config.CHAT_CONTEXT,
            idle_seconds=config.MODEL_IDLE_SECONDS,
            start_seconds=config.MODEL_START_SECONDS,
            restarts=config.MODEL_RESTARTS,
            chat_device=None,
            on_device_chosen=lambda name: self.bridge.send(DeviceChosen(name)),
        )
        self.client = LlamaClient(self.supervisor, max_chars=config.EMBEDDING_MAX_CHARS)
        self.core = CoreHost(
            config.database_path(),
            self.bridge,
            calibration=Calibration(config.EMBEDDING_BASELINE, config.NEAR_DUPLICATE),
            history_messages=config.HISTORY_MESSAGES,
            embedding_identity=_embedding_identity(),
            device_loaded=self.supervisor.remember_device,
        )

        self.thread = QThread()
        self.thread.setObjectName("cognia-model")
        self.worker = ChatWorker(self.client, self.client, self.client)
        self.worker.moveToThread(self.thread)
        self.thread.start()

        self._wire()

    def _wire(self) -> None:
        window, bridge, send = self.window, self.bridge, self.bridge.send
        window.pauseMenuRequested.connect(self._open_menu)
        window.hideCompanionRequested.connect(self._toggle_companion)
        window.nudgeRequested.connect(self._show_nudge)
        window.resumed.connect(self._resume)

        # What the user did, into the core.
        window.messageSent.connect(lambda text: send(SendMessage(text)))
        window.conversationChosen.connect(lambda cid: send(OpenConversation(cid)))
        window.newConversationRequested.connect(lambda: send(NewConversation()))
        window.first_run.confirmed.connect(lambda tid: send(ChooseCharacter(tid)))
        window.character.firstRunRequested.connect(lambda: send(OfferCharacters()))
        window.character.restoreRequested.connect(lambda vid: send(RestoreVersion(vid)))
        window.memory.removeRequested.connect(lambda entry: send(RemoveEntry(entry)))
        window.memory.correctRequested.connect(
            lambda entry, text: send(CorrectEntry(entry, text))
        )
        window.memory.eraseRequested.connect(
            lambda level: send(PreviewErasure(Level(level)))
        )

        # What the core decided, onto this thread. Each slot is a method of this
        # object, so Qt delivers it here and never on the core thread.
        bridge.ready.connect(self._ready)
        bridge.characterShown.connect(self._character_shown)
        bridge.templatesShown.connect(self._templates_shown)
        bridge.screenRequested.connect(self._screen_requested)
        bridge.characterFailed.connect(self._character_failed)
        bridge.conversationLoaded.connect(self._conversation_loaded)
        bridge.conversationsChanged.connect(self._conversations_changed)
        bridge.messageAppended.connect(self._message_appended)
        bridge.replyFinished.connect(self._reply_finished)
        bridge.replyNotSaved.connect(self._reply_not_saved)
        bridge.replyFailed.connect(self._reply_failed)
        bridge.memoryShown.connect(self._memory_shown)
        bridge.memoryFailed.connect(self._memory_failed)
        bridge.erasurePreviewed.connect(self._erasure_previewed)
        bridge.erasureReported.connect(self._erasure_reported)
        bridge.coreFailed.connect(self._core_failed)

        # Model work: the core asks, the model thread answers into the core.
        # The answers go straight into the queue on the model thread.
        bridge.askPrepare.connect(self.worker.prepare)
        bridge.askReply.connect(self.worker.request)
        bridge.askEmbed.connect(self.worker.embed)
        direct = Qt.ConnectionType.DirectConnection
        self.worker.prepared.connect(self._post_prepared, direct)
        self.worker.finished.connect(self._post_reply, direct)
        self.worker.failed.connect(self._post_failure, direct)
        self.worker.embedded.connect(self._post_vectors, direct)
        self.worker.chunk.connect(window.chat.appendChunk)

        self.menu.paused.connect(self._pause)
        self.menu.hideCompanionRequested.connect(self._toggle_companion)

        self.tray.activated.connect(self._tray_activated)
        self.app.aboutToQuit.connect(self._shutdown)

    # ── from the model thread into the core ───────────────────────────────

    def _post_prepared(self, prepared: Prepared) -> None:
        self.bridge.send(TurnPrepared(prepared))

    def _post_reply(self, text: str) -> None:
        self.bridge.send(ReplyArrived(text))

    def _post_failure(self, text: str) -> None:
        self.bridge.send(ReplyLost(text))

    def _post_vectors(self, pairs) -> None:
        self.bridge.send(VectorsMade(tuple(pairs)))

    # ── from the core onto the views ──────────────────────────────────────

    @Slot()
    def _ready(self) -> None:
        self.window.setLoading(False)

    @Slot(object, object, object, str)
    def _character_shown(self, version, earlier, since, history_error: str) -> None:
        name = version.name if version else ""
        self.window.setNeedsCharacter(version is None)
        self.window.memory.setCharacterName(name)
        self.window.overlay.setCharacterName(name)
        if version is None:
            self.window.chat.setCharacter("", "", None)
            return
        self.window.chat.setCharacter(version.name, version.role, since)
        self.window.character.setCharacter(version, earlier)
        if history_error:
            self.window.character.showHistoryError(history_error)

    @Slot(object, object, str)
    def _templates_shown(self, templates, in_force, error: str) -> None:
        self.window.first_run.setTemplates(templates, in_force)
        if error:
            self.window.first_run.showError(error)
        self.window.showFirstRun()

    @Slot(str)
    def _screen_requested(self, screen_id: str) -> None:
        self.window.showApplication(screen_id)

    @Slot(str)
    def _character_failed(self, text: str) -> None:
        self.window.first_run.showError(text)

    @Slot(object)
    def _conversation_loaded(self, messages) -> None:
        self.window.chat.loadConversation(messages)

    @Slot(object, str)
    def _conversations_changed(self, conversations, current_id: str) -> None:
        self.window.chat.setConversations(conversations, current_id)

    @Slot(object)
    def _message_appended(self, message) -> None:
        self.window.chat.appendMessage(message)
        self.window.chat.beginReply()

    @Slot(str, str)
    def _reply_finished(self, text: str, note: str) -> None:
        self.window.chat.endReply(text, note)

    @Slot(str, str)
    def _reply_not_saved(self, text: str, error: str) -> None:
        self.window.chat.endReply(text)
        self.window.chat.showError(error)

    @Slot(str)
    def _reply_failed(self, text: str) -> None:
        self.window.chat.showError(text)

    @Slot(str)
    def _core_failed(self, text: str) -> None:
        """An erasure that waits says so in its own dialog; its report never
        comes. Any other failed step is told in the chat."""
        self.window.setLoading(False)
        dialog = self._erase_dialog
        if dialog is not None and dialog.isVisible() and dialog.working:
            dialog.showStopped()
            return
        self.window.chat.showError(text)

    @Slot(object, object)
    def _memory_shown(self, items, commitments) -> None:
        self.window.memory.setEntries(items, commitments)

    @Slot(str)
    def _memory_failed(self, text: str) -> None:
        self.window.memory.showError(text)

    @Slot(object, object, object)
    def _erasure_previewed(self, level, counts, name) -> None:
        dialog = EraseDialog(level, counts, name, self.window)
        dialog.confirmed.connect(lambda: self._erase(dialog, level))
        dialog.retryRequested.connect(lambda: self._erase(dialog, level))
        dialog.centre_on(self.window.body)
        dialog.show()
        self._erase_dialog = dialog

    @Slot(object)
    def _erasure_reported(self, report) -> None:
        if self._erase_dialog is not None:
            self._erase_dialog.showReport(report)

    def _erase(self, dialog: EraseDialog, level: Level) -> None:
        # Nothing from a reply in flight may be kept after the erasure.
        self.worker.cancel()
        self.window.chat.endReply()
        dialog.showWorking()
        self.bridge.send(Erase(level))

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

    # ── start and stop ────────────────────────────────────────────────────

    def start(self) -> None:
        """Show the window at once; the core fills it when its data is ready."""
        self.window.chat.setMaxChars(config.MESSAGE_MAX_CHARS)
        self.window.centre_on_screen()
        self.window.show()
        self.window.setLoading(True)

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
        self.core.start()

    def _shutdown(self) -> None:
        """A reply in flight is abandoned and not written down. The core finishes
        the command it is on, then closes the database."""
        self.worker.cancel()
        self.thread.quit()
        self.thread.wait(5000)
        self.supervisor.stop()
        self.client.close()
        self.bridge.send(Stop())
        self.core.join(_CORE_STOP_SECONDS)


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
