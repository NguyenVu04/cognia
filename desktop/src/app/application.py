"""Starting Cognia.

Creates the QApplication, registers the vendored fonts, applies the style
sheet, and builds the three surfaces — the main window, the companion on the
desktop, and the tray icon — then joins them to the core through
``screens``, ``companion_wiring``, ``voice_wiring`` and ``tray``. This is the
only module that knows about all of them.

It also starts the two other threads. The core thread holds the data and every
decision; this thread only shows what the core sends and reports what the user
did. The model thread talks to the model servers.
"""

from __future__ import annotations

import argparse
import sys
import threading
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QThread, QTimer, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from src.app import config
from src.app.bridge import Bridge
from src.app.chat_worker import ChatWorker, Prepared
from src.app.commands import (
    DeviceChosen,
    PresenceReported,
    ReplyArrived,
    ReplyLost,
    SendMessage,
    SetAwareness,
    Stop,
    SummaryMade,
    ToolRequested,
    TurnPrepared,
    VectorsMade,
    WindowOpened,
    Worded,
)
from src.app.companion_wiring import CompanionWiring
from src.app.core_host import CoreHost
from src.app.screens import Screens
from src.app.single_instance import SingleInstance
from src.app.tray import Tray
from src.app.voice_wiring import VoiceWiring
from src.domain.memory.models import Calibration
from src.domain.tools.models import ToolCall
from src.infrastructure.ai.llama_client import LlamaClient
from src.infrastructure.ai.mcp_tools import McpTools
from src.infrastructure.ai.supervisor import ModelSupervisor
from src.infrastructure.desktop.native_frame import NativeFrame
from src.infrastructure.desktop.startup import StartupEntry, StartupFailed
from src.infrastructure.presence.sampler import PresenceSampler
from src.infrastructure.presence.win32_source import Win32PresenceSource
from src.infrastructure.storage.dictionary import SqliteDictionary
from src.infrastructure.voice.transcriber import Transcriber, TranscriptionServer
from src.ui import fonts, theme
from src.ui.widgets.frameless import NATIVE_FRAME
from src.ui.windows.companion_window import CompanionWindow
from src.ui.windows.main_window import MainWindow
from src.utils import paths

DICTIONARY = "oewn.sqlite3"
SINGLE_INSTANCE_KEY = "cognia-desktop"
# How long the core may take to finish its last command when Cognia quits.
_CORE_STOP_SECONDS = 10


def _embedding_identity() -> str | None:
    """The embedding model as its file name and size, or ``None`` if missing."""
    path = config.model_path(config.EMBEDDING_MODEL)
    return f"{path.name}:{path.stat().st_size}" if path.is_file() else None


def start_command() -> str:
    """The line that starts Cognia quietly when Windows starts."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}" --background'
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    if windowless.is_file():
        python = windowless
    main = Path(__file__).resolve().parents[1] / "__main__.py"
    return f'"{python}" "{main}" --background'


class _FrameAttacher(QObject):
    """Gives each frameless window the native shadow when it first shows."""

    def __init__(self, frame: NativeFrame) -> None:
        super().__init__()
        self._frame = frame

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.Show
            and isinstance(watched, QWidget)
            and watched.isWindow()
            and watched.property(NATIVE_FRAME)
        ):
            self._frame.attach(int(watched.winId()))
        return False


class Cognia(QObject):
    """Holds the windows, and starts the core thread and the model thread."""

    def __init__(self, app: QApplication, *, background: bool = False) -> None:
        super().__init__()
        self.app = app
        self.background = background
        self.awareness_on = False
        self._sampler: PresenceSampler | None = None
        self._presence_stop = threading.Event()
        self.startup = StartupEntry(start_command())

        self.window = MainWindow()
        self.companion = CompanionWindow()
        self.bridge = Bridge()
        self.supervisor = ModelSupervisor(
            config.model_path(config.LLAMA_SERVER_VULKAN),
            config.model_path(config.LLAMA_SERVER_CPU),
            config.model_path(config.CHAT_MODEL),
            config.model_path(config.EMBEDDING_MODEL),
            context=config.CHAT_CONTEXT,
            cache_ram_mib=config.CHAT_CACHE_RAM_MIB,
            idle_seconds=config.MODEL_IDLE_SECONDS,
            start_seconds=config.MODEL_START_SECONDS,
            restarts=config.MODEL_RESTARTS,
            chat_device=None,
            on_device_chosen=self._device_chosen,
        )
        self.client = LlamaClient(
            self.supervisor,
            max_chars=config.EMBEDDING_MAX_CHARS,
            reply_max_tokens=config.REPLY_MAX_TOKENS,
            interpret_max_tokens=config.INTERPRET_MAX_TOKENS,
            summary_max_tokens=config.SUMMARY_MAX_TOKENS,
        )
        self.transcriber = Transcriber(
            TranscriptionServer(
                config.model_path(config.WHISPER_SERVER),
                config.model_path(config.SPEECH_MODEL),
            )
        )
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
            self.client,
            self.client,
            self.client,
            ask_core=self._ask_core,
            dictionary=SqliteDictionary(paths.resource_dir("dictionary", DICTIONARY)),
            transcriber=self.transcriber,
            add_ons=lambda servers: McpTools(servers),
        )
        self.worker.moveToThread(self.thread)
        self.thread.start()

        self.screens = Screens(self)
        self.companion_wiring = CompanionWiring(self)
        self.voice = VoiceWiring(self)
        self.tray = Tray(self)
        self._wire_model()
        self.app.aboutToQuit.connect(self._shutdown)

    def _wire_model(self) -> None:
        """The core asks, the model thread answers straight into the queue."""
        bridge, worker = self.bridge, self.worker
        bridge.askPrepare.connect(worker.prepare)
        bridge.askReply.connect(worker.request)
        bridge.askEmbed.connect(worker.embed)
        bridge.askSummary.connect(worker.summarize)
        bridge.askWord.connect(worker.word)
        bridge.addOnsChanged.connect(worker.setAddOns)
        bridge.watchForPause.connect(self._watch_for_pause)
        direct = Qt.ConnectionType.DirectConnection
        worker.prepared.connect(self._post_prepared, direct)
        worker.finished.connect(self._post_reply, direct)
        worker.failed.connect(
            lambda turn, text: bridge.send(ReplyLost(turn, text)), direct
        )
        worker.embedded.connect(
            lambda pairs: bridge.send(VectorsMade(tuple(pairs))), direct
        )
        worker.summarized.connect(lambda done: bridge.send(SummaryMade(done)), direct)
        worker.worded.connect(lambda job, text: bridge.send(Worded(job, text)), direct)
        worker.chunk.connect(self.window.chat.appendChunk)
        worker.toolStarted.connect(self.window.chat.showWorking)
        worker.browserRequested.connect(self._open_browser)

    # ── from the model thread into the core ───────────────────────────────

    def _post_prepared(self, prepared: Prepared) -> None:
        self.bridge.send(TurnPrepared(prepared))

    def _post_reply(self, replied) -> None:
        self.bridge.send(ReplyArrived(replied.turn_id, replied.text, replied.results))

    def _ask_core(self, call: ToolCall, now: datetime) -> Future:
        """On the model thread: hand a tool to the core, which answers into the
        returned future."""
        answer: Future = Future()
        self.bridge.send(ToolRequested(call, now, answer))
        return answer

    def _device_chosen(self, name: str) -> None:
        self.bridge.send(DeviceChosen(name))

    @Slot(str)
    def _open_browser(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    # ── actions the wiring shares ─────────────────────────────────────────

    def now(self) -> datetime:
        return datetime.now().astimezone()

    def send_message(self, text: str) -> None:
        # A summary in the background must not delay the reply to this.
        self.worker.cancel_summary()
        self.voice.speaker.stop()
        self.bridge.send(SendMessage(text))

    def show_window(self) -> None:
        first = not self.window.isVisible()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        if first:
            self.bridge.send(WindowOpened())

    def sync_companion_labels(self, hidden: bool, name: str) -> None:
        self.window.sidebar.setCompanionHidden(hidden, name)
        self.tray.set_companion_label(hidden, name)

    def toggle_awareness(self, on: bool) -> None:
        # Reading stops at once, before the core has recorded the choice.
        if not on:
            self.stop_sampler()
        self.bridge.send(SetAwareness(on))

    def awareness_changed(self, on: bool) -> None:
        self.awareness_on = on
        if on and not self.tray.paused:
            self._start_sampler()
        else:
            self.stop_sampler()

    def set_start_with_windows(self, on: bool) -> None:
        try:
            self.startup.enable() if on else self.startup.disable()
        except StartupFailed as error:
            self.window.settings.startup.showError(str(error))
        self.window.settings.startup.setStartWithWindows(self.startup.enabled())

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

    def stop_sampler(self) -> None:
        """Stop reading at once; the thread ends on its own within a second."""
        self._presence_stop.set()
        self._sampler = None

    def _watch_for_pause(self) -> None:
        if self._sampler is not None:
            self._sampler.watch_for_pause()

    # ── start and stop ────────────────────────────────────────────────────

    def start(self) -> None:
        """Show the window at once, unless Windows started Cognia; the core
        fills it when its data is ready."""
        self.window.chat.setMaxChars(config.MESSAGE_MAX_CHARS)
        self.window.settings.startup.setStartWithWindows(self.startup.enabled())
        self.window.centre_on_screen()
        if not self.background:
            self.window.show()
            self.window.setLoading(True)
        # After the window shows, so the slow import never delays it.
        QTimer.singleShot(0, self.worker, self.worker.warm_up)
        self.tray.show()
        self.core.start()

    def quit(self) -> None:
        self.window.allowClose()
        self.app.quit()

    def _shutdown(self) -> None:
        """A reply in flight is abandoned and not written down. The core finishes
        the command it is on, then closes the database."""
        self.worker.cancel()
        self.worker.cancel_summary()
        # Their ends are recorded before the core stops.
        self.companion.stopActivity()
        self.stop_sampler()
        self.voice.close()
        self.thread.quit()
        self.thread.wait(5000)
        self.supervisor.stop()
        self.client.close()
        self.transcriber.close()
        self.bridge.send(Stop())
        self.core.join(_CORE_STOP_SECONDS)


def _palette() -> QPalette:
    """Placeholder text is a palette role in Qt, not a style-sheet property."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.PlaceholderText, theme.TEXT_FAINT)
    palette.setColor(QPalette.ColorRole.Text, theme.TEXT)
    palette.setColor(QPalette.ColorRole.WindowText, theme.TEXT)
    palette.setColor(QPalette.ColorRole.Window, theme.BG_WINDOW)
    palette.setColor(QPalette.ColorRole.Base, theme.BG_INSET)
    palette.setColor(QPalette.ColorRole.Button, theme.BG_CARD)
    palette.setColor(QPalette.ColorRole.ButtonText, theme.TEXT)
    palette.setColor(QPalette.ColorRole.Highlight, theme.ACCENT)
    palette.setColor(QPalette.ColorRole.HighlightedText, theme.ON_ACCENT)
    return palette


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cognia")
    parser.add_argument(
        "--background",
        action="store_true",
        help="start in the tray with no window, as Windows does",
    )
    arguments, qt_arguments = parser.parse_known_args(argv)

    app = QApplication([sys.argv[0], *qt_arguments])
    app.setApplicationName("Cognia")
    app.setWindowIcon(QIcon(str(paths.resource("logo.ico"))))
    app.setQuitOnLastWindowClosed(False)
    instance = SingleInstance(SINGLE_INSTANCE_KEY)
    if not instance.claim():
        return 0

    config.load()
    fonts.load()
    app.setFont(theme.font(14))
    app.setPalette(_palette())
    app.setStyleSheet(theme.stylesheet())
    frame = NativeFrame()
    app.installNativeEventFilter(frame)
    attacher = _FrameAttacher(frame)
    app.installEventFilter(attacher)

    cognia = Cognia(app, background=arguments.background)
    instance.activated.connect(cognia.show_window)
    cognia.start()
    return app.exec()
