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
import threading
from concurrent.futures import Future
from datetime import datetime

from PySide6.QtCore import QObject, QPoint, Qt, QThread, QTimer, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QPalette
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from src.app import config
from src.app.bridge import Bridge
from src.app.chat_worker import ChatWorker, Prepared
from src.app.commands import (
    ActivityEnded,
    ChooseCharacter,
    Command,
    CorrectEntry,
    DeleteConversation,
    DeviceChosen,
    Erase,
    NewConversation,
    OfferCharacters,
    OpenConversation,
    PresenceReported,
    PreviewConversationDeletion,
    PreviewErasure,
    RemoveEntry,
    ReplyArrived,
    ReplyLost,
    RestoreVersion,
    SendMessage,
    SetAwareness,
    Stop,
    SummaryMade,
    ToolRequested,
    TurnPrepared,
    VectorsMade,
)
from src.app.core_host import CoreHost
from src.domain.erasure.models import Level
from src.domain.memory.models import Calibration
from src.domain.tools.models import ToolCall
from src.infrastructure.ai.llama_client import LlamaClient
from src.infrastructure.ai.supervisor import ModelSupervisor
from src.infrastructure.presence.sampler import PresenceSampler
from src.infrastructure.presence.win32_source import Win32PresenceSource
from src.infrastructure.storage.dictionary import SqliteDictionary
from src.ui import fonts, icons, theme
from src.ui.dialogs.delete_conversation_dialog import DeleteConversationDialog
from src.ui.dialogs.erase_dialog import EraseDialog
from src.ui.dialogs.tray_menu import TrayMenu
from src.ui.views import sample_data
from src.ui.windows.companion_window import CompanionWindow
from src.ui.windows.main_window import MainWindow
from src.utils import paths

_PAUSE_LABELS = {option.id: option.paused_label for option in sample_data.PAUSE_OPTIONS}
DICTIONARY = "oewn.sqlite3"
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
        self._delete_dialog: DeleteConversationDialog | None = None
        self._paused = False
        self._awareness_on = False
        self._sampler: PresenceSampler | None = None
        self._presence_stop = threading.Event()

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
            history_max_chars=config.HISTORY_MAX_CHARS,
            embedding_identity=_embedding_identity(),
            device_loaded=self.supervisor.remember_device,
        )

        self.thread = QThread()
        self.thread.setObjectName("cognia-model")
        self.worker = ChatWorker(
            self.client, self.client, self.client, ask_core=self._ask_core,
            dictionary=SqliteDictionary(paths.resource_dir("dictionary", DICTIONARY)),
        )
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
        window.messageSent.connect(self._send_message)
        window.conversationChosen.connect(lambda cid: send(OpenConversation(cid)))
        window.newConversationRequested.connect(lambda: send(NewConversation()))
        window.deleteConversationRequested.connect(
            lambda cid: send(PreviewConversationDeletion(cid))
        )
        window.first_run.confirmed.connect(lambda tid: send(ChooseCharacter(tid)))
        window.character.firstRunRequested.connect(lambda: send(OfferCharacters()))
        window.character.restoreRequested.connect(lambda vid: send(RestoreVersion(vid)))
        window.memory.removeRequested.connect(lambda entry: send(RemoveEntry(entry)))
        window.memory.correctRequested.connect(
            lambda entry, text: send(CorrectEntry(entry, text))
        )
        window.desk.awarenessToggled.connect(self._toggle_awareness)
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
        bridge.conversationDeletionPreviewed.connect(self._deletion_previewed)
        bridge.conversationFailed.connect(self._reply_failed)
        bridge.messageAppended.connect(self._message_appended)
        bridge.replyFinished.connect(self._reply_finished)
        bridge.replyNotSaved.connect(self._reply_not_saved)
        bridge.replyFailed.connect(self._reply_failed)
        bridge.memoryShown.connect(self._memory_shown)
        bridge.memoryFailed.connect(self._memory_failed)
        bridge.erasurePreviewed.connect(self._erasure_previewed)
        bridge.erasureReported.connect(self._erasure_reported)
        bridge.coreFailed.connect(self._core_failed)
        bridge.expressionChanged.connect(self.companion.setExpression)
        bridge.gestureShown.connect(self.companion.playGesture)
        bridge.activityStarted.connect(self._activity_started)
        bridge.awarenessChanged.connect(self._awareness_changed)
        self.companion.activityEnded.connect(
            lambda name, seconds: send(ActivityEnded(name, seconds))
        )

        # Model work: the core asks, the model thread answers into the core.
        # The answers go straight into the queue on the model thread.
        bridge.askPrepare.connect(self.worker.prepare)
        bridge.askReply.connect(self.worker.request)
        bridge.askEmbed.connect(self.worker.embed)
        bridge.askSummary.connect(self.worker.summarize)
        direct = Qt.ConnectionType.DirectConnection
        self.worker.prepared.connect(self._post_prepared, direct)
        self.worker.finished.connect(self._post_reply, direct)
        self.worker.failed.connect(self._post_failure, direct)
        self.worker.embedded.connect(self._post_vectors, direct)
        self.worker.summarized.connect(self._post_summary, direct)
        self.worker.chunk.connect(window.chat.appendChunk)
        self.worker.toolStarted.connect(self._tool_started)
        self.worker.browserRequested.connect(self._open_browser)

        self.menu.paused.connect(self._pause)
        self.menu.hideCompanionRequested.connect(self._toggle_companion)

        self.tray.activated.connect(self._tray_activated)
        self.app.aboutToQuit.connect(self._shutdown)

    # ── from the model thread into the core ───────────────────────────────

    def _post_prepared(self, prepared: Prepared) -> None:
        self.bridge.send(TurnPrepared(prepared))

    def _post_reply(self, replied) -> None:
        self.bridge.send(
            ReplyArrived(replied.turn_id, replied.text, replied.results)
        )

    def _ask_core(self, call: ToolCall, now: datetime) -> Future:
        """On the model thread: hand a tool to the core, which answers into the
        returned future."""
        answer: Future = Future()
        self.bridge.send(ToolRequested(call, now, answer))
        return answer

    def _post_failure(self, turn_id: int, text: str) -> None:
        self.bridge.send(ReplyLost(turn_id, text))

    def _post_vectors(self, pairs) -> None:
        self.bridge.send(VectorsMade(tuple(pairs)))

    def _post_summary(self, done) -> None:
        self.bridge.send(SummaryMade(done))

    def _send_message(self, text: str) -> None:
        # A summary in the background must not delay the reply to this.
        self.worker.cancel_summary()
        self.bridge.send(SendMessage(text))

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

    @Slot(object, int, int)
    def _deletion_previewed(self, conversation, messages: int, lines: int) -> None:
        dialog = DeleteConversationDialog(
            conversation.title, messages, lines, self.window
        )
        dialog.confirmed.connect(
            lambda: self.bridge.send(DeleteConversation(conversation.id))
        )
        dialog.centre_on(self.window.body)
        dialog.show()
        self._delete_dialog = dialog

    @Slot(object)
    def _message_appended(self, message) -> None:
        self.window.chat.appendMessage(message)
        self.window.chat.beginReply()

    @Slot(str, str, str)
    def _reply_finished(self, text: str, note: str, check: str) -> None:
        self.window.chat.endReply(text, note, check)

    # ── desk awareness ────────────────────────────────────────────────────

    def _toggle_awareness(self, on: bool) -> None:
        # Reading stops at once, before the core has recorded the choice.
        if not on:
            self._stop_sampler()
        self.bridge.send(SetAwareness(on))

    @Slot(bool, str)
    def _awareness_changed(self, on: bool, error: str) -> None:
        self._awareness_on = on
        self.window.desk.setAwareness(on)
        self.window.desk.showError(error)
        if on and not self._paused:
            self._start_sampler()
        else:
            self._stop_sampler()

    def _start_sampler(self) -> None:
        if self._sampler is not None and self._sampler.is_alive():
            return
        self._presence_stop = threading.Event()
        self._sampler = PresenceSampler(
            Win32PresenceSource(),
            report=lambda change: self.bridge.offer(PresenceReported(change)),
            failed=lambda text: self.bridge.send(SetAwareness(False, text)),
            stop=self._presence_stop,
        )
        self._sampler.start()

    def _stop_sampler(self) -> None:
        self._presence_stop.set()
        if self._sampler is not None:
            self._sampler.join(2)
            self._sampler = None

    @Slot(str, object)
    def _activity_started(self, name: str, steps) -> None:
        self.companion.playActivity(name, steps)
        # Nobody can do an exercise with a companion that is not on screen.
        if not self.companion.isVisible():
            self.companion.stopActivity()

    @Slot(str)
    def _tool_started(self, label: str) -> None:
        self.window.chat.showWorking(label)
        self.companion.playGesture("think")

    @Slot(str)
    def _open_browser(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    @Slot(str, str)
    def _reply_not_saved(self, text: str, error: str) -> None:
        self.window.chat.endReply(text)
        self.window.chat.showError(error)

    @Slot(str)
    def _reply_failed(self, text: str) -> None:
        self.window.chat.showError(text)

    @Slot(str, object)
    def _core_failed(self, text: str, command: Command | None) -> None:
        """Say it where the user asked for the step: an erasure in its dialog,
        whose report never comes, the count of one on the memory page, and
        anything else in the chat."""
        self.window.setLoading(False)
        dialog = self._erase_dialog
        match command:
            case Erase() if dialog is not None and dialog.isVisible():
                dialog.showStopped()
            case PreviewErasure():
                self.window.memory.showError(text)
            case _:
                self.window.chat.showError(text)

    @Slot(object)
    def _memory_shown(self, items) -> None:
        self.window.memory.setEntries(items)

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
        self.worker.cancel_summary()
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
        self._paused = True
        self._stop_sampler()
        self.window.showPaused(_PAUSE_LABELS[option_id])
        self.companion.stopActivity()
        self.companion.hide()

    def _resume(self) -> None:
        self._paused = False
        if self._awareness_on:
            self._start_sampler()
        self.window.hidePaused()
        if not self.companion_hidden:
            self.companion.show()

    def _toggle_companion(self) -> None:
        self.companion_hidden = not self.companion_hidden
        if self.companion_hidden:
            self.companion.stopActivity()
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
        # After the window shows, so the slow import never delays it.
        QTimer.singleShot(0, self.worker, self.worker.warm_up)

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
        self.worker.cancel_summary()
        # Their ends are recorded before the core stops.
        self.companion.stopActivity()
        self._stop_sampler()
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
