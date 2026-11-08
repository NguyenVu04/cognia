"""Companion — the conversation screen.

The header names the character and its feeling; the column holds the
conversation; the composer takes typed or spoken words. The view holds no
conversation of its own: it is told what to show, and it reports what the user
did. Which model answers, and where the words are kept, are decided in
``app/``.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from datetime import date, datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from src.domain.conversation.models import COMPANION, Conversation, Message
from src.ui import formatting, theme
from src.ui.dialogs.conversation_menu import ConversationMenu
from src.ui.widgets.buttons import Button, IconButton
from src.ui.widgets.message_bubble import WRITING, MessageRow, TypingIndicator
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import StyledWidget, bottom_rule
from src.ui.widgets.typography import caption, label, paragraph

# A bubble being filled in as the model speaks. It is not stored yet, so it has
# no identity and no time.
_DRAFT_REPLY = Message("", "", COMPANION, "", datetime.min)

# The counter appears once a message reaches this share of the limit.
_COUNTER_FROM = 0.8
# Pieces of a reply arriving within this time are drawn together.
_REDRAW_MS = 40

NO_EMOJI = "Emoji can’t be sent."
NO_INVISIBLE = "Invisible characters can’t be sent."

_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xFE00, 0xFE0F),
    (0x20E3, 0x20E3),
)
# Control, format, private, surrogate and unassigned code points make the line
# shown differ from the line kept.
_INVISIBLE = {"Cc", "Cf", "Co", "Cs", "Cn"}


def refusal(text: str) -> str:
    """Why ``text`` cannot be sent, or an empty string if it can. Letters with
    accents and typographic punctuation, such as ’ — …, are allowed."""
    if any(_is_emoji(ch) for ch in text):
        return NO_EMOJI
    if any(unicodedata.category(ch) in _INVISIBLE for ch in text):
        return NO_INVISIBLE
    return ""


def _is_emoji(ch: str) -> bool:
    point = ord(ch)
    return any(low <= point <= high for low, high in _EMOJI_RANGES)


class ChatView(QWidget):
    messageSent = Signal(str)
    conversationChosen = Signal(str)
    newConversationRequested = Signal()
    deleteConversationRequested = Signal(str)
    feelingWhyRequested = Signal()
    #: The message id and 1, -1, or 0 to take the rating back.
    rated = Signal(str, int)
    micToggled = Signal()
    stopSpeakingRequested = Signal()
    #: The user started typing, which stops the voice.
    typingStarted = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._locked = False
        # An empty conversation is already new, so another is not started.
        self._empty = True
        self._reply_row: MessageRow | None = None
        self._reply_text = ""
        self._max_chars: int | None = None
        self._redraw = QTimer(self)
        self._redraw.setSingleShot(True)
        self._redraw.setInterval(_REDRAW_MS)
        self._redraw.timeout.connect(self._draw_reply)

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._header())
        column.addWidget(self._messages(), 1)
        column.addWidget(self._composer())

    # ── building ──────────────────────────────────────────────────────────

    def _header(self) -> QWidget:
        header = bottom_rule()
        row = QHBoxLayout(header)
        row.setContentsMargins(32, 18, 24, 14)
        row.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        names = QHBoxLayout()
        names.setSpacing(10)
        self.name = label("", font=theme.font(20, 800))
        names.addWidget(self.name)
        self.feeling = Button("", size="small", variant="ghost", icon_name="sparkle")
        self.feeling.setToolTip("Why do you feel this way?")
        self.feeling.clicked.connect(self.feelingWhyRequested)
        self.feeling.setVisible(False)
        names.addWidget(self.feeling)
        names.addStretch(1)
        titles.addLayout(names)
        self.role = caption("", px=12.5)
        titles.addWidget(self.role)
        row.addLayout(titles, 1)

        self.menu = ConversationMenu(self)
        self.menu.chosen.connect(self.conversationChosen)
        self.menu.newRequested.connect(self.requestNewConversation)
        self.menu.deleteRequested.connect(self.deleteConversationRequested)
        self.picker = Button("New conversation", size="small", icon_name="chat-circle")
        self.picker.setToolTip("Earlier conversations")
        self.picker.clicked.connect(self._open_menu)
        row.addWidget(self.picker, 0, Qt.AlignmentFlag.AlignVCenter)
        self.new_button = IconButton("plus", "New conversation (Ctrl+N)", px=16, box=34)
        self.new_button.clicked.connect(self.requestNewConversation)
        row.addWidget(self.new_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self._update_new()
        return header

    def _messages(self) -> QWidget:
        self.pane = ScrollPane(padding=(22, 32, 22, 32), spacing=14)
        typing = QHBoxLayout()
        typing.setContentsMargins(0, 0, 0, 0)
        self.typing = TypingIndicator()
        typing.addWidget(self.typing)
        typing.addStretch(1)
        self.typing_row = QWidget()
        self.typing_row.setLayout(typing)
        self.typing_row.setVisible(False)
        self.pane.column.addWidget(self.typing_row)
        self.pane.column.addStretch(1)
        return self.pane

    def _composer(self) -> QWidget:
        bar = StyledWidget()
        bar.setRules(f"border-top: 1px solid {theme.css(theme.HAIRLINE)};")
        column = QVBoxLayout(bar)
        column.setContentsMargins(28, 12, 28, 18)
        column.setSpacing(8)

        self.listening = QWidget()
        listen_row = QHBoxLayout(self.listening)
        listen_row.setContentsMargins(4, 0, 4, 0)
        listen_row.setSpacing(10)
        self.listen_text = caption("Listening… press the microphone again to stop.")
        listen_row.addWidget(self.listen_text)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setFixedSize(120, 6)
        self.level.setStyleSheet(
            "QProgressBar {"
            f"background: {theme.css(theme.BG_INSET)}; border: 0; border-radius: 3px;"
            "}"
            "QProgressBar::chunk {"
            f"background: {theme.css(theme.ACCENT)}; border-radius: 3px;"
            "}"
        )
        listen_row.addWidget(self.level)
        listen_row.addStretch(1)
        self.listening.setVisible(False)
        column.addWidget(self.listening)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.mic = IconButton(
            "microphone", "Talk instead of typing", px=19, box=42, checkable=True
        )
        self.mic.clicked.connect(self.micToggled)
        row.addWidget(self.mic)
        self.draft = QLineEdit()
        self.draft.setPlaceholderText("Say something…")
        self.draft.setFont(theme.font(14.5))
        self.draft.setStyleSheet(
            "QLineEdit { border-radius: 12px; padding: 11px 14px; }"
        )
        self.draft.returnPressed.connect(self._send)
        self.draft.textChanged.connect(self._count)
        self.draft.textEdited.connect(lambda _: self.typingStarted.emit())
        row.addWidget(self.draft, 1)
        self.stop_voice = IconButton("speaker-slash", "Stop speaking", px=18, box=42)
        self.stop_voice.clicked.connect(self.stopSpeakingRequested)
        self.stop_voice.setVisible(False)
        row.addWidget(self.stop_voice)
        self.send = Button("Send", variant="primary", icon_name="paper-plane-right")
        self.send.clicked.connect(self._send)
        row.addWidget(self.send)
        column.addLayout(row)
        self.counter = caption("")
        self.counter.setVisible(False)
        column.addWidget(self.counter, 0, Qt.AlignmentFlag.AlignRight)
        return bar

    # ── the user's half ───────────────────────────────────────────────────

    def _send(self) -> None:
        """Hand the draft up, if there is one, it can be sent, and nothing is
        already in flight."""
        text = self.draft.text().strip()
        if not text or self._busy or not self._sendable():
            return
        self.draft.clear()
        self.messageSent.emit(text)

    def _sendable(self) -> bool:
        text = self.draft.text()
        too_long = self._max_chars is not None and len(text) > self._max_chars
        return not too_long and not refusal(text)

    def _count(self) -> None:
        """Say why the draft cannot go, or show its length near the limit.
        Nothing the user typed is cut without their knowing."""
        text = self.draft.text()
        refused = refusal(text)
        limit = self._max_chars
        over = limit is not None and len(text) > limit
        if refused:
            self.counter.setText(refused)
        elif limit is not None:
            self.counter.setText(f"{len(text):,} / {limit:,}")
        near = limit is not None and len(text) >= limit * _COUNTER_FROM
        self.counter.setVisible(bool(refused) or near)
        colour = theme.DANGER if refused or over else theme.TEXT_FAINT
        self.counter.setStyleSheet(
            f"color: {theme.css(colour)}; background: transparent;"
        )
        self.send.setEnabled(not self._busy and self._sendable())

    def _open_menu(self) -> None:
        if self.menu.isVisible():
            self.menu.hide()
            return
        below = self.picker.mapToGlobal(self.picker.rect().bottomLeft())
        below.setY(below.y() + 6)
        self.menu.popup_under(below)

    # ── what the application tells it to show ─────────────────────────────

    def setConversations(
        self, conversations: Sequence[Conversation], current_id: str | None = None
    ) -> None:
        self.menu.setConversations(conversations, current_id)
        current = next((c for c in conversations if c.id == current_id), None)
        self.picker.setText(current.title if current else "New conversation")

    def loadConversation(self, messages: Sequence[Message]) -> None:
        """Replace the column with a conversation, scrolled to its end."""
        self.endReply()
        # The typing row and the trailing stretch stay; the rest is replaced.
        while self.pane.column.count() > 2:
            item = self.pane.column.takeAt(0)
            if (widget := item.widget()) is not None:
                widget.deleteLater()
        for message in messages:
            self._add(self._row(message))
        self._settle()
        self._empty = not messages
        self._update_new()

    def appendMessage(self, message: Message) -> None:
        self._add(self._row(message))
        self._settle()
        self._empty = False
        self._update_new()

    def requestNewConversation(self) -> None:
        """Ask for a new conversation, unless this one is empty or a reply is
        still coming."""
        if self._can_start_new():
            self.newConversationRequested.emit()

    def _can_start_new(self) -> bool:
        return not self._locked and not self._empty

    def _update_new(self) -> None:
        allowed = self._can_start_new()
        self.new_button.setEnabled(allowed)
        self.menu.setStartEnabled(allowed)

    def beginReply(self) -> None:
        """Say that the companion is working. Never a blank pause."""
        self._busy = True
        self.send.setEnabled(False)
        self._lock(True)
        self._reply_row = None
        self._reply_text = ""
        self.typing.setText(WRITING)
        self.typing_row.setVisible(True)
        self._settle()

    def showWorking(self, text: str) -> None:
        """Say which tool the companion is using, while no words have come."""
        self.typing.setText(f"{text}…")
        if self._reply_row is None and self._busy:
            self.typing_row.setVisible(True)
            self._settle()

    def appendChunk(self, text: str) -> None:
        if self._reply_row is None:
            self.typing_row.setVisible(False)
            self._reply_row = MessageRow(_DRAFT_REPLY)
            self._add(self._reply_row)
        self._reply_text += text
        if not self._redraw.isActive():
            self._redraw.start()

    def _draw_reply(self) -> None:
        if self._reply_row is not None:
            self._reply_row.setText(self._reply_text)
            self._settle()

    def endReply(
        self,
        text: str | None = None,
        note: str = "",
        check: str = "",
        message_id: str = "",
    ) -> None:
        """Finish the reply. ``note`` is the chip of what was stored, ``check``
        the chip of numbers no tool gave, and ``message_id`` the stored reply,
        which can then be rated."""
        self._redraw.stop()
        row = self._reply_row
        if row is not None:
            row.setText(text or self._reply_text)
            if note:
                row.setNote(note)
            if check:
                row.setCheck(check)
            if message_id:
                row.setMessageId(message_id)
                row.rated.connect(self.rated)
        self._busy = False
        self.send.setEnabled(self._sendable())
        self._lock(False)
        self._reply_row = None
        self._reply_text = ""
        self.typing_row.setVisible(False)
        self._settle()

    def showError(self, text: str) -> None:
        """Said by the application, not put in the character's mouth. A
        half-finished reply is thrown away."""
        if self._reply_row is not None:
            self._reply_row.hide()
            self._reply_row.deleteLater()
            self._reply_row = None
        self.endReply()
        self.showNotice(text)

    def showNotice(self, text: str) -> None:
        """A line from the application itself, never stored."""
        self._add(_Notice(text))
        self._settle()

    def setCharacter(self, name: str, role: str, since: date | None) -> None:
        """The character in force, and the day the first one was chosen."""
        self.name.setText(name)
        together = f" · together since {formatting.long_date(since)}" if since else ""
        self.role.setText(f"{role}{together}")

    def setFeeling(self, feeling: str) -> None:
        """The name of the feeling now, or "" with moods off."""
        self.feeling.setText(feeling)
        self.feeling.setVisible(bool(feeling))

    def setMaxChars(self, limit: int) -> None:
        self._max_chars = limit
        self._count()

    def setListening(self, listening: bool) -> None:
        self.mic.setChecked(listening)
        self.listening.setVisible(listening)
        self.level.setValue(0)

    def setLevel(self, level: float) -> None:
        """The loudness of the microphone, 0 to 1."""
        self.level.setValue(round(max(0.0, min(1.0, level)) * 100))

    def sendSpoken(self, text: str) -> None:
        """Send recognised words at once, after anything already typed, so the
        user can talk while the window is hidden. Words that cannot be sent
        now, for example while a reply is still coming, stay in the composer."""
        current = self.draft.text().strip()
        self.draft.setText(f"{current} {text}" if current else text)
        self._send()

    def setSpeaking(self, speaking: bool) -> None:
        self.stop_voice.setVisible(speaking)

    def setTalkHint(self, sequence: str) -> None:
        tip = (
            f"Talk instead of typing ({sequence} anywhere)"
            if sequence
            else ("Talk instead of typing")
        )
        self.mic.setToolTip(tip)

    def _lock(self, locked: bool) -> None:
        """A reply belongs to the conversation it was asked in, so the user
        cannot leave that conversation until the reply is done."""
        if locked:
            self.menu.hide()
        self.picker.setEnabled(not locked)
        self._locked = locked
        self._update_new()

    # ── the column ────────────────────────────────────────────────────────

    def _row(self, message: Message) -> MessageRow:
        row = MessageRow(message)
        row.rated.connect(self.rated)
        return row

    def _add(self, widget: QWidget) -> None:
        """Insert above the typing row, which sits above the trailing stretch."""
        self.pane.column.insertWidget(self.pane.column.count() - 2, widget)

    def _settle(self) -> None:
        self.pane.refresh()
        QTimer.singleShot(0, self.pane.scroll_to_bottom)


class _Notice(QWidget):
    """A line from the application itself — not a message, so never stored."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.addStretch(1)
        notice = paragraph(
            text, font=theme.font(13), colour=theme.TEXT_SECONDARY, max_width=460
        )
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(notice)
        row.addStretch(1)
