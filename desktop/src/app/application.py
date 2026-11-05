"""Starting Cognia.

Creates the QApplication, registers the vendored fonts, applies the style
sheet, and wires the three surfaces to each other. This is the only module that
knows about all three.

It is also the only module that knows about all three *layers*. The views below
it render domain models and report what the user did; the adapters beside it
keep the data on disk and run the model servers on this machine; neither
imports the other. The joins are all here.

Still no observation: nothing reads the operating system, and the companion on
the desktop watches nothing. What the user says is kept because they said it,
and they see each line that is kept.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, QPoint, QThread, Signal, Slot
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from src.app import config
from src.app.chat_worker import ChatWorker, Prepared, TurnRequest
from src.domain.character import rules as character_rules
from src.domain.character.character_service import CharacterService
from src.domain.companion import rules as companion_rules
from src.domain.companion.companion_service import CompanionService
from src.domain.conversation import rules
from src.domain.conversation.models import COMPANION, USER, Message
from src.domain.emotion.emotion_service import EmotionService
from src.domain.erasure.erasure_service import ErasureService
from src.domain.erasure.models import Level
from src.domain.events.models import EventKind, Payload
from src.domain.memory import rules as memory_rules
from src.domain.memory.memory_service import MemoryService
from src.domain.memory.models import (
    Calibration,
    Commitment,
    Entry,
    MemoryItem,
    Scored,
    Selection,
    Vector,
)
from src.domain.ports import (
    CharacterCatalogUnavailable,
    CharacterStoreFailed,
    ErasureFailed,
    EventLogFailed,
    MemoryStoreFailed,
)
from src.domain.safety import rules as safety_rules
from src.infrastructure.ai.llama_client import LlamaClient
from src.infrastructure.ai.supervisor import ModelSupervisor
from src.infrastructure.storage.character_catalog import TomlCharacterCatalog
from src.infrastructure.storage.character_store import SqliteCharacterStore
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.erasure_store import SqliteErasureStore
from src.infrastructure.storage.event_log import SqliteEventLog
from src.infrastructure.storage.memory_store import SqliteMemoryStore
from src.infrastructure.storage.settings_store import SqliteSettings
from src.infrastructure.storage.sqlite_store import (
    UNTITLED,
    SqliteConversationStore,
    title_from,
)
from src.ui import fonts, icons, theme
from src.ui.dialogs.erase_dialog import EraseDialog
from src.ui.dialogs.tray_menu import TrayMenu
from src.ui.views import sample_data
from src.ui.windows.companion_window import CompanionWindow
from src.ui.windows.main_window import MainWindow
from src.utils import paths

_PAUSE_LABELS = {option.id: option.paused_label for option in sample_data.PAUSE_OPTIONS}

NOT_SAVED = "The reply could not be saved, so nothing from it was kept. Try again."


@dataclass(frozen=True)
class _Turn:
    """One message of the user on its way to a reply."""

    id: int
    conversation_id: str
    message_id: str
    history: tuple[Message, ...]


@dataclass(frozen=True)
class _Ready:
    """What the reply of a turn will store once it arrives."""

    selection: Selection | None
    importance: int
    vectors: Mapping[str, Vector]
    recalled: tuple[Scored, ...]
    lines: tuple[str, ...]


def _offset(moment: datetime) -> int:
    return int(moment.utcoffset().total_seconds() // 60)


def _now() -> datetime:
    return datetime.now().astimezone()


class Cognia(QObject):
    """Holds the windows, the stores, and the thread the model answers on."""

    #: Emitted on the GUI thread, delivered on the worker's. Qt queues each,
    #: which is the whole reason the window keeps painting while the model
    #: takes its time.
    askPrepare = Signal(object)
    askModel = Signal(str, object, str)
    askEmbed = Signal(object)
    #: Emitted on the model thread when a GPU is chosen; saved on this one.
    deviceChosen = Signal(str)

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.companion_hidden = False

        self.window = MainWindow()
        self.companion = CompanionWindow()
        self.menu = TrayMenu()

        self.tray = QSystemTrayIcon(icons.icon("chat-circle", 32, theme.ACCENT))
        self.tray.setToolTip("Cognia")

        self.database = Database.open(config.database_path())
        self.store = SqliteConversationStore(self.database)
        character_store = SqliteCharacterStore(self.database)
        self.characters = CharacterService(
            character_store, TomlCharacterCatalog(paths.resource("characters.toml"))
        )
        self.memory = MemoryService(SqliteMemoryStore(self.database))
        self.erasure = ErasureService(SqliteErasureStore(self.database))
        self.settings = SqliteSettings(self.database)
        self.companion_service = CompanionService(
            SqliteEventLog(self.database), EmotionService(character_store)
        )
        self.state = self._fold()
        self.calibration = Calibration(config.EMBEDDING_BASELINE, config.NEAR_DUPLICATE)

        self.version = None
        self.prompt = ""
        self.conversation = self.store.latest() or self.store.create(_now())
        self._turn_count = 0
        self._turn: _Turn | None = None
        self._ready: _Ready | None = None
        self._erase_dialog: EraseDialog | None = None

        self.supervisor = ModelSupervisor(
            config.model_path(config.LLAMA_SERVER_VULKAN),
            config.model_path(config.LLAMA_SERVER_CPU),
            config.model_path(config.CHAT_MODEL),
            config.model_path(config.EMBEDDING_MODEL),
            context=config.CHAT_CONTEXT,
            idle_seconds=config.MODEL_IDLE_SECONDS,
            start_seconds=config.MODEL_START_SECONDS,
            restarts=config.MODEL_RESTARTS,
            chat_device=self.settings.chat_device(),
            on_device_chosen=self.deviceChosen.emit,
        )
        self.client = LlamaClient(self.supervisor, max_chars=config.EMBEDDING_MAX_CHARS)

        self.thread = QThread()
        self.thread.setObjectName("cognia-model")
        self.worker = ChatWorker(self.client, self.client, self.client)
        self.worker.moveToThread(self.thread)
        self.thread.start()

        self._wire()

    def _wire(self) -> None:
        window = self.window
        window.pauseMenuRequested.connect(self._open_menu)
        window.hideCompanionRequested.connect(self._toggle_companion)
        window.nudgeRequested.connect(self._show_nudge)
        window.resumed.connect(self._resume)

        window.messageSent.connect(self._say)
        window.conversationChosen.connect(self._open_conversation)
        window.newConversationRequested.connect(self._new_conversation)

        window.first_run.confirmed.connect(self._choose)
        window.character.firstRunRequested.connect(self._offer_change)
        window.character.restoreRequested.connect(self._restore)

        window.memory.removeRequested.connect(self._remove)
        window.memory.correctRequested.connect(self._correct)
        window.memory.eraseRequested.connect(self._erase_requested)

        self.askPrepare.connect(self.worker.prepare)
        self.askModel.connect(self.worker.request)
        self.askEmbed.connect(self.worker.embed)
        self.worker.prepared.connect(self._prepared)
        self.worker.chunk.connect(window.chat.appendChunk)
        self.worker.finished.connect(self._replied)
        self.worker.failed.connect(self._failed)
        self.worker.embedded.connect(self._embedded)
        self.deviceChosen.connect(self._save_device)

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
        """The user has said something. Record it, show it, then prepare."""
        if self.version is None:
            self._offer_first_run()
            return
        now = _now()
        message = self.store.append(Message.new(self.conversation.id, USER, text, now))
        if self.conversation.title == UNTITLED:
            self.store.retitle(self.conversation.id, title_from(text))
            self.conversation = self._reread(self.conversation.id)

        self.window.chat.appendMessage(message)
        self.window.chat.beginReply()
        self._refresh_picker()

        history = tuple(
            self.store.history(self.conversation.id, config.HISTORY_MESSAGES)
        )
        self._turn_count += 1
        self._turn = _Turn(self._turn_count, self.conversation.id, message.id, history)
        self._ready = None
        self.askPrepare.emit(
            TurnRequest(
                turn_id=self._turn.id,
                system_prompt=self.prompt,
                history=history,
                entries=tuple(self._entries()),
                crisis=safety_rules.tripwire(text),
                today=now.date(),
                now=now,
                calibration=self.calibration,
            )
        )

    @Slot(object)
    def _prepared(self, prepared: Prepared) -> None:
        """Choose what to keep, and ask for the reply with what it draws on."""
        turn = self._turn
        if turn is None or prepared.turn_id != turn.id:
            return  # a turn that was abandoned
        selection, lines, importance = None, (), 1
        if prepared.found is not None:
            importance = prepared.found.importance
            selection = memory_rules.select(
                prepared.found, self._entries(), prepared.vectors, self.calibration
            )
            lines = (*selection.facts, *(c.text for c in selection.commitments))
        self._ready = _Ready(
            selection, importance, prepared.vectors, prepared.recalled, lines
        )
        zone = _now().tzinfo
        remembered = [
            memory_rules.recalled_line(s.entry, zone) for s in prepared.recalled
        ]
        turn_text = rules.turn_text("", remembered, rules.show_back_instruction(lines))
        self.askModel.emit(self.prompt, list(turn.history), turn_text)

    @Slot(str)
    def _replied(self, text: str) -> None:
        """A reply arrived whole. It, and everything the turn keeps, is recorded
        only now and in one transaction, never mid-stream."""
        turn, ready = self._turn, self._ready
        self._turn = self._ready = None
        now = _now()
        note = ""
        if ready is not None and ready.lines:
            missing = [
                line for line in ready.lines if not memory_rules.shows_back(text, line)
            ]
            note = memory_rules.stored_note(missing, now.date())
        conversation_id = turn.conversation_id if turn else self.conversation.id
        try:
            with self.database.transaction():
                reply = self.store.append(
                    Message.new(conversation_id, COMPANION, text, now)
                )
                state = self.state
                if turn is not None and ready is not None:
                    state = self._keep(turn, ready, reply, now, state)
        except (MemoryStoreFailed, EventLogFailed) as error:
            self.window.chat.endReply(text)
            self.window.chat.showError(str(error) or NOT_SAVED)
            return
        self.state = state
        self.window.chat.endReply(text, note)
        self._refresh_picker()
        self._refresh_memory()
        self._embed_missing()

    def _keep(self, turn: _Turn, ready: _Ready, reply: Message, now: datetime, state):
        """Store the chosen lines with their events, and link what the reply drew
        on. Runs inside the caller's transaction."""
        if ready.selection is not None:
            stored = self.memory.remember(
                ready.selection, ready.importance, turn.message_id, ready.vectors, now
            )
            for entry in stored:
                if isinstance(entry, MemoryItem):
                    kind = EventKind.MEMORY_STORED
                    payload = {"memory_item_id": entry.id}
                else:
                    kind = EventKind.COMMITMENT_ADDED
                    payload = {"commitment_id": entry.id}
                state = self._record(state, now, kind, payload)
        self.memory.use(reply.id, [s.entry for s in ready.recalled], now)
        return state

    @Slot(str)
    def _failed(self, text: str) -> None:
        """No reply, so nothing from the turn is kept."""
        self._turn = self._ready = None
        self.window.chat.showError(text)

    def _new_conversation(self) -> None:
        if not self.store.history(self.conversation.id, 1):
            return  # already sitting in an empty one; don't pile up more
        self.conversation = self.store.create(_now())
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

    # ── memory ────────────────────────────────────────────────────────────

    def _entries(self) -> list[Entry]:
        try:
            return self.memory.entries()
        except MemoryStoreFailed:
            return []

    def _refresh_memory(self) -> None:
        try:
            entries = self.memory.entries()
        except MemoryStoreFailed as error:
            self.window.memory.showError(str(error))
            return
        self.window.memory.setEntries(
            [e for e in entries if isinstance(e, MemoryItem)],
            [e for e in entries if isinstance(e, Commitment)],
        )

    def _correct(self, entry: Entry, text: str) -> None:
        try:
            self.memory.correct(entry, text)
        except ValueError:
            pass  # the view refuses a blank line before it gets here
        except MemoryStoreFailed as error:
            self.window.memory.showError(str(error))
            return
        self._refresh_memory()
        self._embed_missing()

    def _remove(self, entry: Entry) -> None:
        now = _now()
        if isinstance(entry, MemoryItem):
            kind, payload = EventKind.MEMORY_REMOVED, {"memory_item_id": entry.id}
        else:
            kind = EventKind.COMMITMENT_CLOSED
            payload = {"commitment_id": entry.id, "finished": False}
        try:
            with self.database.transaction():
                self.memory.remove(entry)
                state = self._record(self.state, now, kind, payload)
        except (MemoryStoreFailed, EventLogFailed) as error:
            self.window.memory.showError(str(error))
            return
        self.state = state
        self._refresh_memory()

    def _embed_missing(self) -> None:
        try:
            missing = self.memory.missing_vectors()
        except MemoryStoreFailed:
            return
        if missing:
            self.askEmbed.emit(missing)

    @Slot(object)
    def _embedded(self, pairs: Sequence[tuple[Entry, Vector]]) -> None:
        for entry, vector in pairs:
            try:
                self.memory.store_vector(entry, vector)
            except MemoryStoreFailed:
                return  # it waits for the next chance

    def _check_embedding_model(self) -> None:
        path = config.model_path(config.EMBEDDING_MODEL)
        if not path.is_file():
            return
        try:
            self.memory.check_model(f"{path.name}:{path.stat().st_size}")
        except MemoryStoreFailed:
            pass

    # ── character ─────────────────────────────────────────────────────────

    def _load_character(self) -> None:
        """Put the version in force everywhere it shows."""
        try:
            self.version = self.characters.current()
        except CharacterStoreFailed:
            self.version = None
        version = self.version
        self.window.setNeedsCharacter(version is None)
        name = version.name if version else ""
        self.window.memory.setCharacterName(name)
        self.window.overlay.setCharacterName(name)
        if version is None:
            self.prompt = ""
            self.window.chat.setCharacter("", "", None)
            return
        self.prompt = (
            f"{rules.system_text(version.description)}\n\n{rules.REASONING_RULE}"
        )
        try:
            history = self.characters.history()
        except CharacterStoreFailed as error:
            self.window.chat.setCharacter(version.name, version.role, None)
            self.window.character.setCharacter(version, [])
            self.window.character.showHistoryError(str(error))
            return
        first = min(history, key=lambda v: v.number)
        self.window.chat.setCharacter(
            version.name, version.role, first.created_at.astimezone().date()
        )
        earlier = [
            (v, character_rules.in_force_until(v, history))
            for v in history
            if v.id != version.id
        ]
        self.window.character.setCharacter(version, earlier)

    def _offer_first_run(self) -> None:
        self._show_templates(None)
        self.window.showFirstRun()

    def _offer_change(self) -> None:
        self._show_templates(self.version.template_id if self.version else None)
        self.window.showFirstRun()

    def _show_templates(self, in_force: str | None) -> None:
        try:
            templates = self.characters.templates()
        except CharacterCatalogUnavailable as error:
            self.window.first_run.setTemplates([], in_force)
            self.window.first_run.showError(str(error))
            return
        self.window.first_run.setTemplates(templates, in_force)

    def _choose(self, template_id: str) -> None:
        first = self.version is None
        self._put_in_force(lambda now: self.characters.choose(template_id, now))
        if self.version is not None:
            self.window.showApplication("chat" if first else "character")

    def _restore(self, version_id: str) -> None:
        self._put_in_force(lambda now: self.characters.restore(version_id, now))

    def _put_in_force(self, add) -> None:
        """Add a version and record ``character_changed`` in one transaction."""
        now = _now()
        try:
            with self.database.transaction():
                version = add(now)
                state = self._record(
                    self.state, now, EventKind.CHARACTER_CHANGED,
                    {"version_id": version.id},
                )
        except (CharacterStoreFailed, EventLogFailed, ValueError) as error:
            self.window.first_run.showError(str(error))
            return
        self.state = state
        self._load_character()

    # ── erasure ───────────────────────────────────────────────────────────

    def _erase_requested(self, level_text: str) -> None:
        level = Level(level_text)
        try:
            counts = self.erasure.preview(level)
        except ErasureFailed as error:
            self.window.memory.showError(str(error))
            return
        name = self.version.name if self.version else None
        dialog = EraseDialog(level, counts, name, self.window)
        dialog.confirmed.connect(lambda: self._erase(dialog, level))
        dialog.retryRequested.connect(lambda: self._erase(dialog, level))
        dialog.centre_on(self.window.body)
        dialog.show()
        self._erase_dialog = dialog

    def _erase(self, dialog: EraseDialog, level: Level) -> None:
        # Nothing from a turn in flight may be kept after the erasure.
        self.worker.cancel()
        self._turn = self._ready = None
        self.window.chat.endReply()
        dialog.showWorking()
        self.app.processEvents()
        report = self.erasure.erase(level)
        dialog.showReport(report)
        self._after_erasure()

    def _after_erasure(self) -> None:
        """Show what is left. The feelings start again at the resting mood of the
        character that remains, if one does."""
        self.state = self._fold()
        self._load_character()
        if self.version is not None:
            now = _now()
            try:
                with self.database.transaction():
                    state = self._record(
                        self.state, now, EventKind.CHARACTER_CHANGED,
                        {"version_id": self.version.id},
                    )
                self.state = state
            except EventLogFailed:
                pass
        self.conversation = self.store.latest() or self.store.create(_now())
        self.window.chat.loadConversation(self.store.history(self.conversation.id))
        self._refresh_picker()
        self._refresh_memory()

    # ── events ────────────────────────────────────────────────────────────

    def _record(self, state, now: datetime, kind: EventKind, payload: Payload):
        return self.companion_service.record(
            state, now, _offset(now), kind, payload, None
        ).state

    def _fold(self):
        try:
            return self.companion_service.start()
        except (EventLogFailed, ValueError):
            return companion_rules.initial_state()

    @Slot(str)
    def _save_device(self, name: str) -> None:
        self.settings.set_chat_device(name)

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
        self.window.chat.setMaxChars(config.MESSAGE_MAX_CHARS)
        self._load_character()
        self.window.chat.loadConversation(self.store.history(self.conversation.id))
        self._refresh_picker()
        self._refresh_memory()
        self._check_embedding_model()
        self._embed_missing()
        if self.version is None:
            self._offer_first_run()

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
        """A reply in flight is abandoned and not written down."""
        self.worker.cancel()
        self.thread.quit()
        self.thread.wait(5000)
        self.supervisor.stop()
        self.client.close()
        self.database.close()


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
