"""Companion — the conversation screen.

The default destination. Header, the message column, and a composer that never
takes focus away from anything else.

The view holds no conversation of its own: it is told what to show, and it
reports what the user typed. Which model answers, and where the words are kept,
are decided in ``app/`` — ``ui/`` is not allowed to know either.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from src.core.models import COMPANION, Conversation, Message
from src.ui import theme
from src.ui.dialogs.conversation_menu import ConversationMenu
from src.ui.views import sample_data
from src.ui.widgets.buttons import accent_button, quiet_button
from src.ui.widgets.message_bubble import MessageRow, TypingIndicator
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import StyledWidget, bottom_rule
from src.ui.widgets.typography import label, paragraph

#: A bubble being filled in as the model speaks. It is never stored, so it
#: carries no identity and no time — only the text, which keeps changing.
_DRAFT_REPLY = Message("", "", COMPANION, "", datetime.min)


class ChatView(QWidget):
    hideCompanionRequested = Signal()
    messageSent = Signal(str)
    conversationChosen = Signal(str)
    newConversationRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        character = sample_data.CHARACTERS[0]
        self._busy = False
        self._reply_row: MessageRow | None = None
        self._reply_text = ""

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        column.addWidget(self._header(character))
        column.addWidget(self._messages(), 1)
        column.addWidget(self._composer())

    def _header(self, character: sample_data.Character) -> QWidget:
        header = bottom_rule()
        row = QHBoxLayout(header)
        row.setContentsMargins(36, 26, 36, 14)
        row.setSpacing(8)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(
            label(character.name, font=theme.font(20, 500), colour=theme.TEXT)
        )
        titles.addWidget(
            label(
                f"{character.role} · {sample_data.TOGETHER_SINCE}",
                font=theme.font(12.5),
                colour=theme.muted(0.5),
            )
        )
        row.addLayout(titles)
        row.addStretch(1)

        self.menu = ConversationMenu(self)
        self.menu.chosen.connect(self.conversationChosen)
        self.menu.newRequested.connect(self.newConversationRequested)

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
        typing.addWidget(TypingIndicator())
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
        self.draft.setStyleSheet("QLineEdit { border-radius: 9px; padding: 12px 15px; }")
        self.draft.returnPressed.connect(self._send)
        row.addWidget(self.draft, 1)

        self.send = accent_button(
            "Send", px=14, radius=9, padding=(13, 20),
            icon_name="paper-plane-right",
        )
        self.send.clicked.connect(self._send)
        row.addWidget(self.send)
        return bar

    # ── the user's half ───────────────────────────────────────────────────

    def _send(self) -> None:
        """Hand the draft up, if there is one and nothing is already in flight."""
        text = self.draft.text().strip()
        if not text or self._busy:
            return
        self.draft.clear()
        self.messageSent.emit(text)

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
        """Say that the companion is working. NFR-06: never a blank pause."""
        self._busy = True
        self.send.setEnabled(False)
        self._reply_row = None
        self._reply_text = ""
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

    def endReply(self, text: str | None = None) -> None:  # noqa: N802 - Qt naming
        if text and self._reply_row is not None:
            self._reply_row.setText(text)
        self._busy = False
        self.send.setEnabled(True)
        self._reply_row = None
        self._reply_text = ""
        self.typing_row.setVisible(False)
        self._settle()

    def showError(self, text: str) -> None:  # noqa: N802 - Qt naming
        """UC-09 E1 — said by the application, not put in the character's mouth.

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
