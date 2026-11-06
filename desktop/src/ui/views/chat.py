"""Companion — the conversation screen.

The default destination. Header, the message column, and a composer that never
takes focus away from anything else.

The view holds no conversation of its own: it is told what to show, and it
reports what the user typed. Which model answers, and where the words are kept,
are decided in ``app/`` — ``ui/`` is not allowed to know either.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from datetime import date, datetime

from PySide6.QtCore import QLocale, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from src.domain.conversation.models import COMPANION, Conversation, Message
from src.ui import theme
from src.ui.dialogs.conversation_menu import ConversationMenu
from src.ui.widgets.buttons import accent_button, quiet_button
from src.ui.widgets.message_bubble import WRITING, MessageRow, TypingIndicator
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import StyledWidget, bottom_rule
from src.ui.widgets.typography import label, paragraph

#: A bubble being filled in as the model speaks. It is never stored, so it
#: carries no identity and no time — only the text, which keeps changing.
_DRAFT_REPLY = Message("", "", COMPANION, "", datetime.min)

#: The counter appears once a message reaches this share of the limit.
_COUNTER_FROM = 0.8

_ENGLISH = QLocale(QLocale.Language.English)

NO_EMOJI = "Emoji can’t be sent."
NO_INVISIBLE = "Invisible characters can’t be sent."

# Emoji blocks, with the selector, keycap and joiner marks that build emoji.
_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xFE00, 0xFE0F),
    (0x20E3, 0x20E3),
)
# Control, format (zero-width, direction overrides), private, surrogate and
# unassigned code points: they make the line shown differ from the line kept.
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
    hideCompanionRequested = Signal()
    messageSent = Signal(str)
    conversationChosen = Signal(str)
    newConversationRequested = Signal()
    deleteConversationRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._reply_row: MessageRow | None = None
        self._reply_text = ""
        self._max_chars: int | None = None

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        column.addWidget(self._header())
        column.addWidget(self._messages(), 1)
        column.addWidget(self._composer())

    def _header(self) -> QWidget:
        header = bottom_rule()
        row = QHBoxLayout(header)
        row.setContentsMargins(36, 26, 36, 14)
        row.setSpacing(8)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.name = label("", font=theme.font(20, 500), colour=theme.TEXT)
        titles.addWidget(self.name)
        self.role = label("", font=theme.font(12.5), colour=theme.muted(0.5))
        titles.addWidget(self.role)
        row.addLayout(titles)
        row.addStretch(1)

        self.menu = ConversationMenu(self)
        self.menu.chosen.connect(self.conversationChosen)
        self.menu.newRequested.connect(self.newConversationRequested)
        self.menu.deleteRequested.connect(self.deleteConversationRequested)

        self.new_button = quiet_button(
            "+", px=12.5, radius=7, padding=(8, 13), fg=theme.muted(0.72)
        )
        self.new_button.setToolTip("New conversation")
        self.new_button.clicked.connect(self.newConversationRequested)
        row.addWidget(self.new_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.picker = quiet_button(
            "New conversation", px=12.5, radius=7, padding=(8, 13),
            fg=theme.muted(0.72), icon_name="chat-circle", gap=7,
        )
        self.picker.clicked.connect(self._open_menu)
        row.addWidget(self.picker, 0, Qt.AlignmentFlag.AlignVCenter)

        self.hide_button = quiet_button(
            "Hide from desktop", px=12.5, radius=7, padding=(8, 13),
            fg=theme.muted(0.72), icon_name="eye-slash", gap=7,
        )
        self.hide_button.clicked.connect(self.hideCompanionRequested)
        row.addWidget(self.hide_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    def _messages(self) -> QWidget:
        self.pane = ScrollPane(padding=(26, 36, 26, 36), spacing=16)

        typing = QHBoxLayout()
        typing.setContentsMargins(0, 0, 0, 0)
        self.typing = TypingIndicator()
        typing.addWidget(self.typing)
        typing.addStretch(1)
        self.typing_row = QWidget()
        self.typing_row.setLayout(typing)
        self.typing_row.setVisible(False)  # shown only while a reply is composed
        self.pane.column.addWidget(self.typing_row)

        self.pane.column.addStretch(1)
        return self.pane

    def _composer(self) -> QWidget:
        bar = StyledWidget()
        bar.setRules(f"border-top: 1px solid {theme.css(theme.HAIRLINE)};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(36, 16, 36, 24)
        row.setSpacing(10)

        self.draft = QLineEdit()
        self.draft.setPlaceholderText("Say something…")
        self.draft.setFont(theme.font(14))
        self.draft.setStyleSheet(
            "QLineEdit { border-radius: 9px; padding: 12px 15px; }"
        )
        self.draft.returnPressed.connect(self._send)
        self.draft.textChanged.connect(self._count)
        row.addWidget(self.draft, 1)

        self.counter = label("", font=theme.font(12), colour=theme.muted(0.45))
        self.counter.setVisible(False)
        row.addWidget(self.counter)

        self.send = accent_button(
            "Send", px=14, radius=9, padding=(13, 20),
            icon_name="paper-plane-right",
        )
        self.send.clicked.connect(self._send)
        row.addWidget(self.send)
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
        """Say why the draft cannot go, or show its length near the limit. Send
        stops instead: nothing the user typed or pasted is cut without their
        knowing."""
        text = self.draft.text()
        refused = refusal(text)
        length = len(text)
        limit = self._max_chars
        over = limit is not None and length > limit
        if refused:
            self.counter.setText(refused)
        elif limit is not None:
            self.counter.setText(f"{length:,} / {limit:,}")
        near = limit is not None and length >= limit * _COUNTER_FROM
        self.counter.setVisible(bool(refused) or near)
        colour = theme.ACCENT_TEXT if refused or over else theme.muted(0.45)
        self.counter.setStyleSheet(
            f"color: {theme.css(colour)}; background: transparent;"
        )
        self.send.setEnabled(not self._busy and self._sendable())

    def _open_menu(self) -> None:
        if self.menu.isVisible():
            self.menu.hide()
            return
        below = self.picker.mapToGlobal(self.picker.rect().bottomLeft())
        below.setY(below.y() + 8)
        self.menu.popup_under(below)

    # ── what the application tells it to show ─────────────────────────────

    def setConversations(  # noqa: N802 - matches Qt naming
        self, conversations: Sequence[Conversation], current_id: str | None = None
    ) -> None:
        self.menu.setConversations(conversations, current_id)
        current = next((c for c in conversations if c.id == current_id), None)
        self.picker.setLabel(current.title if current else "New conversation")

    def loadConversation(  # noqa: N802 - matches Qt naming
        self, messages: Sequence[Message]
    ) -> None:
        """Replace the column with a conversation, scrolled to its end."""
        self.endReply()
        # The typing row and the trailing stretch are furniture; everything
        # above them is the conversation being replaced.
        while self.pane.column.count() > 2:
            item = self.pane.column.takeAt(0)
            if (widget := item.widget()) is not None:
                widget.deleteLater()
        for message in messages:
            self._add(MessageRow(message))
        self._settle()

    def appendMessage(self, message: Message) -> None:  # noqa: N802 - Qt naming
        self._add(MessageRow(message))
        self._settle()

    def beginReply(self) -> None:  # noqa: N802 - Qt naming
        """Say that the companion is working. Never a blank pause."""
        self._busy = True
        self.send.setEnabled(False)
        self._lock(True)
        self._reply_row = None
        self._reply_text = ""
        self.typing.setText(WRITING)
        self.typing_row.setVisible(True)
        self._settle()

    def showWorking(self, label: str) -> None:  # noqa: N802 - Qt naming
        """Say which tool the companion is using, while no words have come."""
        self.typing.setText(f"{label}…")
        if self._reply_row is None and self._busy:
            self.typing_row.setVisible(True)
            self._settle()

    def appendChunk(self, text: str) -> None:  # noqa: N802 - Qt naming
        if self._reply_row is None:
            # The first words have arrived, so the indicator has done its job.
            self.typing_row.setVisible(False)
            self._reply_row = MessageRow(_DRAFT_REPLY)
            self._add(self._reply_row)
        self._reply_text += text
        self._reply_row.setText(self._reply_text)
        self._settle()

    def endReply(  # noqa: N802 - Qt naming
        self, text: str | None = None, note: str = "", check: str = ""
    ) -> None:
        """Finish the reply. ``note`` is the chip under it, if anything was
        stored, and ``check`` the chip for numbers no tool gave."""
        if text and self._reply_row is not None:
            self._reply_row.setText(text)
        if note and self._reply_row is not None:
            self._reply_row.setNote(note)
        if check and self._reply_row is not None:
            self._reply_row.setCheck(check)
        self._busy = False
        self.send.setEnabled(self._sendable())
        self._lock(False)
        self._reply_row = None
        self._reply_text = ""
        self.typing_row.setVisible(False)
        self._settle()

    def showError(self, text: str) -> None:  # noqa: N802 - Qt naming
        """Said by the application, not put in the character's mouth.

        A half-finished reply is thrown away rather than left on screen looking
        like something the companion meant to say.
        """
        if self._reply_row is not None:
            self._reply_row.setParent(None)
            self._reply_row.deleteLater()
            self._reply_row = None
        self.endReply()
        self._add(_Notice(text))
        self._settle()

    def setHideLabel(self, text: str) -> None:  # noqa: N802 - matches Qt naming
        """Track whether the companion is on screen, as the tray does."""
        self.hide_button.setLabel(text)

    def setCharacter(  # noqa: N802 - matches Qt naming
        self, name: str, role: str, since: date | None
    ) -> None:
        """The character in force, and the day the first one was chosen."""
        self.name.setText(name)
        together = f" · together since {_ENGLISH.toString(since, 'd MMMM')}"
        self.role.setText(f"{role}{together if since else ''}")

    def setMaxChars(self, limit: int) -> None:  # noqa: N802 - matches Qt naming
        """The longest message the user can send, in characters."""
        self._max_chars = limit
        self._count()

    def _lock(self, locked: bool) -> None:
        """A reply belongs to the conversation it was asked in, so the user
        cannot leave that conversation until the reply is done."""
        if locked:
            self.menu.hide()
        self.picker.setEnabled(not locked)
        self.new_button.setEnabled(not locked)

    # ── the column ────────────────────────────────────────────────────────

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
        row.setSpacing(0)
        row.addStretch(1)
        row.addWidget(
            paragraph(
                text,
                font=theme.font(12.5),
                colour=theme.muted(0.5),
                line_height=1.55,
                max_width=420,
            )
        )
        row.addStretch(1)
