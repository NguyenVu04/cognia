"""The main window and its dialogs, joined to the core.

What the user did goes into the core as commands; what the core decided comes
back as bridge signals and is shown here. Every slot is a method of an object
on the GUI thread, so Qt delivers each signal on this thread.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Slot

from src.app.commands import (
    AddToolServer,
    ChooseCharacter,
    CloseHintShown,
    CorrectEntry,
    DeleteConversation,
    Erase,
    ExcludeApp,
    ExplainFeeling,
    IncludeApp,
    MarkLearnedWrong,
    NewConversation,
    OfferCharacters,
    OpenConversation,
    PreviewConversationDeletion,
    PreviewErasure,
    RateMessage,
    RemoveEntry,
    RemoveToolServer,
    RestoreVersion,
    SaveSpeechSettings,
    SetHotkey,
    SetSpeakAloud,
    UndoLearned,
    WindowOpened,
)
from src.domain.awareness.models import DeskTime
from src.domain.erasure.models import Level
from src.infrastructure.ai.supervisor import CHAT, ServerState
from src.ui import formatting
from src.ui.dialogs.add_tool_server_dialog import AddToolServerDialog
from src.ui.dialogs.close_notice import CloseNotice
from src.ui.dialogs.delete_conversation_dialog import DeleteConversationDialog
from src.ui.dialogs.erase_dialog import EraseDialog
from src.ui.dialogs.feeling_dialog import FeelingDialog
from src.ui.views.navigation import COMPANION
from src.ui.views.settings.view import DESK, ERASE, SPEAKING_UP
from src.ui.widgets import sidebar

if TYPE_CHECKING:
    from src.app.application import Cognia

_MODEL_POLL_MS = 1500
_MODEL_STATES = {
    ServerState.STOPPED: (sidebar.READY, ""),
    ServerState.STARTING: (sidebar.LOADING, "Loading the model…"),
    ServerState.RESTARTING: (sidebar.LOADING, "Starting the model again…"),
    ServerState.READY: (sidebar.READY, "Thinking on the graphics card"),
    ServerState.FALLBACK_CPU: (sidebar.READY, "Thinking on the processor"),
    ServerState.FAILED: (
        sidebar.UNAVAILABLE,
        "The model could not start. Try again, or restart Cognia.",
    ),
}


def desk_text(desk: DeskTime | None) -> str:
    if desk is None:
        return ""
    if desk.today_minutes == 0 and not desk.at_desk:
        return "I haven't seen you at your desk yet today."
    text = (
        f"You've been at your desk for {formatting.duration(desk.today_minutes)} today."
    )
    if desk.since_break_minutes is not None:
        text += (
            f" Since your last break: {formatting.duration(desk.since_break_minutes)}."
        )
    return text


class Screens(QObject):
    def __init__(self, cognia: Cognia) -> None:
        super().__init__()
        self.c = cognia
        self._dialog = None
        self._erase_dialog: EraseDialog | None = None
        self._close_hint_shown = True
        self._name = ""
        self._model_state = None
        self._poll = QTimer(self)
        self._poll.setInterval(_MODEL_POLL_MS)
        self._poll.timeout.connect(self._poll_model)
        self._wire()

    def _wire(self) -> None:
        c, window, bridge, send = (
            self.c,
            self.c.window,
            self.c.bridge,
            self.c.bridge.send,
        )
        chat, memory, settings = window.chat, window.memory, window.settings

        chat.messageSent.connect(c.send_message)
        chat.conversationChosen.connect(lambda cid: send(OpenConversation(cid)))
        chat.newConversationRequested.connect(lambda: send(NewConversation()))
        chat.deleteConversationRequested.connect(
            lambda cid: send(PreviewConversationDeletion(cid))
        )
        chat.feelingWhyRequested.connect(lambda: send(ExplainFeeling()))
        chat.rated.connect(lambda mid, rating: send(RateMessage(mid, rating)))
        window.first_run.confirmed.connect(lambda tid: send(ChooseCharacter(tid)))
        window.character.firstRunRequested.connect(lambda: send(OfferCharacters()))
        window.character.restoreRequested.connect(lambda vid: send(RestoreVersion(vid)))
        window.desk_step.decided.connect(self._desk_decided)
        memory.removeRequested.connect(lambda entry: send(RemoveEntry(entry)))
        memory.correctRequested.connect(
            lambda entry, text: send(CorrectEntry(entry, text))
        )
        memory.undoRequested.connect(lambda lid: send(UndoLearned(lid)))
        memory.markWrongRequested.connect(lambda lid: send(MarkLearnedWrong(lid)))
        memory.feelingWhyRequested.connect(lambda: send(ExplainFeeling()))
        memory.deskSettingsRequested.connect(lambda: window.openSettings(DESK))
        memory.eraseSettingsRequested.connect(lambda: window.openSettings(ERASE))
        settings.speaking_up.saveRequested.connect(
            lambda s: send(SaveSpeechSettings(s))
        )
        settings.desk.awarenessToggled.connect(c.toggle_awareness)
        settings.desk.excludeRequested.connect(lambda name: send(ExcludeApp(name)))
        settings.desk.includeRequested.connect(lambda name: send(IncludeApp(name)))
        settings.voice.speakAloudToggled.connect(lambda on: send(SetSpeakAloud(on)))
        settings.voice.hotkeyChosen.connect(lambda seq: send(SetHotkey(seq)))
        settings.tools.addRequested.connect(self._add_tool_server)
        settings.tools.removeRequested.connect(lambda sid: send(RemoveToolServer(sid)))
        settings.startup.startWithWindowsToggled.connect(c.set_start_with_windows)
        settings.erase.eraseRequested.connect(
            lambda level: send(PreviewErasure(Level(level)))
        )
        window.sidebar.retryRequested.connect(self._retry_model)
        window.closeRequested.connect(self._close)

        bridge.ready.connect(self._ready)
        bridge.characterShown.connect(self._character_shown)
        bridge.templatesShown.connect(self._templates_shown)
        bridge.screenRequested.connect(self._screen_requested)
        bridge.characterFailed.connect(window.first_run.showError)
        bridge.conversationLoaded.connect(chat.loadConversation)
        bridge.conversationsChanged.connect(chat.setConversations)
        bridge.conversationDeletionPreviewed.connect(self._deletion_previewed)
        bridge.conversationFailed.connect(chat.showError)
        bridge.messageAppended.connect(self._message_appended)
        bridge.replyFinished.connect(chat.endReply)
        bridge.replyNotSaved.connect(self._reply_not_saved)
        bridge.replyFailed.connect(chat.showError)
        bridge.noticeShown.connect(chat.showNotice)
        bridge.memoryShown.connect(memory.setEntries)
        bridge.memoryFailed.connect(memory.showError)
        bridge.learnedShown.connect(memory.setLearned)
        bridge.feelingShown.connect(self._feeling_shown)
        bridge.feelingExplained.connect(self._feeling_explained)
        bridge.deskShown.connect(self._desk_shown)
        bridge.erasurePreviewed.connect(self._erasure_previewed)
        bridge.erasureReported.connect(self._erasure_reported)
        bridge.coreFailed.connect(self._core_failed)
        bridge.awarenessChanged.connect(self._awareness_changed)
        bridge.speechSettingsShown.connect(settings.speaking_up.setSettings)
        bridge.speechSettingsSaved.connect(self._speech_saved)
        bridge.voiceSettingsShown.connect(self._voice_shown)
        bridge.toolServersShown.connect(settings.tools.setServers)
        bridge.toolServersFailed.connect(settings.tools.showError)
        bridge.closeHintShown.connect(self._set_close_hint)
        bridge.greetingShown.connect(self._greeting_shown)

    # ── the window ────────────────────────────────────────────────────────

    def _ready(self) -> None:
        self.c.window.setLoading(False)
        self._poll.start()
        self._poll_model()
        if self.c.window.isVisible():
            self.c.bridge.send(WindowOpened())

    def _poll_model(self) -> None:
        state = self.c.supervisor.state(CHAT)
        if state != self._model_state:
            self._model_state = state
            self.c.window.sidebar.setModelState(*_MODEL_STATES[state])

    def _retry_model(self) -> None:
        self.c.supervisor.retry()
        self._poll_model()
        QTimer.singleShot(0, self.c.worker, self.c.worker.warm_up)

    def _close(self) -> None:
        """Hide, and say once that Cognia keeps running."""
        self.c.window.hide()
        if not self._close_hint_shown:
            self._close_hint_shown = True
            notice = CloseNotice(self._name)
            notice.acknowledged.connect(lambda: self.c.bridge.send(CloseHintShown()))
            notice.adjustSize()
            screen = self.c.window.screen().availableGeometry()
            notice.move(screen.center() - notice.rect().center())
            notice.show()
            self._dialog = notice

    @Slot(bool)
    def _set_close_hint(self, shown: bool) -> None:
        self._close_hint_shown = shown

    # ── character ─────────────────────────────────────────────────────────

    @Slot(object, object, object, str)
    def _character_shown(self, version, earlier, since, history_error: str) -> None:
        window = self.c.window
        self._name = version.name if version else ""
        window.setNeedsCharacter(version is None)
        window.overlay.setCharacterName(self._name)
        self.c.companion_wiring.set_character(version)
        if version is None:
            window.chat.setCharacter("", "", None)
            return
        window.chat.setCharacter(version.name, version.role, since)
        window.character.setCharacter(version, earlier)
        if history_error:
            window.character.showHistoryError(history_error)

    @Slot(object, object, str)
    def _templates_shown(self, templates, in_force, error: str) -> None:
        window = self.c.window
        window.first_run.setTemplates(templates, in_force)
        if error:
            window.first_run.showError(error)
        window.showFirstRun()

    @Slot(str)
    def _screen_requested(self, screen_id: str) -> None:
        if screen_id == "onboarding":
            self.c.window.tips_step.setHotkey(self.c.voice.hotkey)
            self.c.window.showOnboarding()
            return
        self.c.window.showApplication(screen_id)

    def _desk_decided(self, on: bool) -> None:
        if on:
            self.c.toggle_awareness(True)
        self.c.window.showTips()

    # ── conversation ──────────────────────────────────────────────────────

    @Slot(object, int, int)
    def _deletion_previewed(self, conversation, messages: int, lines: int) -> None:
        dialog = DeleteConversationDialog(
            conversation.title, messages, lines, self.c.window
        )
        dialog.confirmed.connect(
            lambda: self.c.bridge.send(DeleteConversation(conversation.id))
        )
        dialog.centre_on(self.c.window)
        dialog.show()
        self._dialog = dialog

    @Slot(object)
    def _message_appended(self, message) -> None:
        self.c.window.chat.appendMessage(message)
        self.c.window.chat.beginReply()

    @Slot(str, str)
    def _reply_not_saved(self, text: str, error: str) -> None:
        self.c.window.chat.endReply(text)
        self.c.window.chat.showError(error)

    @Slot(object, str)
    def _greeting_shown(self, message, note: str) -> None:
        self.c.window.chat.appendMessage(message)
        self.c.voice.say_text(message.text)

    @Slot(str, object)
    def _core_failed(self, text: str, command) -> None:
        """Say it where the user asked for the step."""
        window = self.c.window
        window.setLoading(False)
        dialog = self._erase_dialog
        match command:
            case Erase() if dialog is not None and dialog.isVisible():
                dialog.showStopped()
            case PreviewErasure():
                window.memory.showError(text)
            case _:
                window.chat.showError(text)

    # ── memory and feelings ───────────────────────────────────────────────

    @Slot(str, str)
    def _feeling_shown(self, feeling: str, rest: str) -> None:
        self.c.window.chat.setFeeling(feeling)
        self.c.window.memory.setFeeling(feeling, rest)

    @Slot(str, object)
    def _feeling_explained(self, name: str, found) -> None:
        dialog = FeelingDialog(name, found, self.c.window)
        dialog.centre_on(self.c.window)
        dialog.show()
        self._dialog = dialog

    @Slot(object, object, object)
    def _desk_shown(self, desk, minutes, excluded) -> None:
        settings = self.c.window.settings.desk
        settings.setToday(desk_text(desk), minutes or {})
        settings.setExcluded(excluded)
        self.c.window.memory.setAppMinutes(minutes)

    @Slot(bool, str)
    def _awareness_changed(self, on: bool, error: str) -> None:
        self.c.window.settings.desk.setAwareness(on)
        self.c.window.settings.desk.showError(error)
        self.c.awareness_changed(on)

    # ── erasure ───────────────────────────────────────────────────────────

    @Slot(object, object, object)
    def _erasure_previewed(self, level, counts, name) -> None:
        dialog = EraseDialog(level, counts, name, self.c.window)
        dialog.confirmed.connect(lambda: self._erase(dialog, level))
        dialog.retryRequested.connect(lambda: self._erase(dialog, level))
        dialog.centre_on(self.c.window)
        dialog.show()
        self._erase_dialog = dialog

    @Slot(object)
    def _erasure_reported(self, report) -> None:
        if self._erase_dialog is not None:
            self._erase_dialog.showReport(report)
        self.c.window.showApplication(COMPANION)

    def _erase(self, dialog: EraseDialog, level: Level) -> None:
        # Nothing from a reply in flight may be kept after the erasure.
        self.c.worker.cancel()
        self.c.worker.cancel_summary()
        self.c.window.chat.endReply()
        dialog.showWorking()
        self.c.bridge.send(Erase(level))

    # ── settings ──────────────────────────────────────────────────────────

    @Slot(str)
    def _speech_saved(self, error: str) -> None:
        section = self.c.window.settings.speaking_up
        if error:
            section.showError(error)
        else:
            section.showSaved()

    @Slot(bool, str)
    def _voice_shown(self, speak_aloud: bool, hotkey: str) -> None:
        voice = self.c.window.settings.voice
        voice.setSpeakAloud(speak_aloud)
        voice.setHotkey(hotkey)
        self.c.voice.set_settings(speak_aloud, hotkey)

    def _add_tool_server(self) -> None:
        dialog = AddToolServerDialog(self.c.window)
        dialog.added.connect(
            lambda d: self.c.bridge.send(
                AddToolServer(d.name, d.transport, d.command, d.args, d.url)
            )
        )
        dialog.centre_on(self.c.window)
        dialog.show()
        self._dialog = dialog

    def open_speaking_up(self) -> None:
        self.c.show_window()
        self.c.window.openSettings(SPEAKING_UP)
