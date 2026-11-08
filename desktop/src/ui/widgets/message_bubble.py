"""Conversation bubbles.

The square corner of a bubble sits on the side of the speaker. A companion
message can carry chips under it — what was stored, or numbers that no tool
gave — and thumbs to rate it once it is stored.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from src.domain.conversation.models import Message
from src.ui import icons, theme
from src.ui.widgets.buttons import IconButton
from src.ui.widgets.surface import Panel
from src.ui.widgets.typography import paragraph, set_paragraph_text

MAX_WIDTH = 480
TEXT_WIDTH = MAX_WIDTH - 32
WRITING = "writing…"
_FONT_PX = 14.5


class MessageRow(QWidget):
    """One message, aligned to its side of the column."""

    #: The message id and the rating: 1, -1, or 0 to take it back.
    rated = Signal(str, int)

    def __init__(self, message: Message, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.message_id = message.id
        from_user = message.from_user
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        if from_user:
            row.addStretch(1)
        stack = QVBoxLayout()
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(6)

        bubble = Panel(
            fill=theme.wash(0.16) if from_user else theme.BG_BUBBLE,
            ring=theme.wash(0.32) if from_user else theme.BORDER_SUBTLE,
            radius=16,
            padding=(11, 15, 11, 15),
        )
        bubble.addRules(
            "border-bottom-right-radius: 4px;" if from_user
            else "border-bottom-left-radius: 4px;"
        )
        bubble.setMaximumWidth(MAX_WIDTH)
        self._text = paragraph(
            message.text, font=theme.font(_FONT_PX), max_width=TEXT_WIDTH,
            selectable=True,
        )
        bubble.body().addWidget(self._text)
        stack.addWidget(bubble)
        self._stack = stack
        self._note: _Chip | None = None
        self._check: _Chip | None = None
        self._thumbs: dict[int, IconButton] = {}
        self._rating = message.rating or 0
        if message.note:
            self.setNote(message.note)
        if not from_user and message.id:
            self._add_thumbs()
        row.addLayout(stack)
        if not from_user:
            row.addStretch(1)

    def setText(self, text: str) -> None:
        """Rewrite the bubble in place, for a reply arriving a piece at a time."""
        set_paragraph_text(
            self._text, text, font=theme.font(_FONT_PX), max_width=TEXT_WIDTH
        )

    def setMessageId(self, message_id: str) -> None:
        """The reply is stored, so it can be rated."""
        self.message_id = message_id
        if not self._thumbs and message_id:
            self._add_thumbs()

    def setNote(self, text: str) -> None:
        """Show the chip of what was stored, in place of any earlier one."""
        if self._note is not None:
            self._note.deleteLater()
        self._note = _Chip(text, "brain")
        self._stack.addWidget(self._note)

    def setCheck(self, text: str) -> None:
        """Show the chip of numbers that came from nothing checked."""
        if self._check is not None:
            self._check.deleteLater()
        self._check = _Chip(text, "warning-circle")
        self._stack.addWidget(self._check)

    def checkText(self) -> str:
        return self._check.text if self._check is not None else ""

    def rating(self) -> int:
        return self._rating

    def _add_thumbs(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(2)
        for value, name, tip in (
            (1, "thumbs-up", "Good reply"),
            (-1, "thumbs-down", "Not a good reply"),
        ):
            button = IconButton(name, tip, px=14, box=28, checkable=True)
            button.clicked.connect(lambda _=False, v=value: self._rate(v))
            self._thumbs[value] = button
            row.addWidget(button)
        row.addStretch(1)
        self._stack.addLayout(row)
        self._paint_thumbs()

    def _rate(self, value: int) -> None:
        self._rating = 0 if self._rating == value else value
        self._paint_thumbs()
        self.rated.emit(self.message_id, self._rating)

    def _paint_thumbs(self) -> None:
        for value, button in self._thumbs.items():
            button.setChecked(self._rating == value)


class _Chip(QWidget):
    """A chip under a companion message."""

    def __init__(self, text: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.text = text
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        chip = Panel(
            fill=theme.wash(0.08), ring=theme.wash(0.26), radius=9,
            padding=(8, 12, 8, 12),
        )
        chip.setMaximumWidth(MAX_WIDTH)
        row = QHBoxLayout()
        row.setSpacing(7)
        row.addWidget(icons.icon_label(icon, 13, theme.ACCENT_TEXT))
        row.addWidget(
            paragraph(
                text, font=theme.font(12.5), colour=theme.ACCENT_TEXT,
                max_width=MAX_WIDTH - 60,
            ),
            1,
        )
        chip.body().addLayout(row)
        outer.addWidget(chip)
        outer.addStretch(1)


class TypingIndicator(Panel):
    """Shown while a reply is being composed: never a blank pause."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            fill=theme.BG_BUBBLE, ring=theme.BORDER_SUBTLE, radius=16,
            padding=(10, 16, 10, 16), parent=parent,
        )
        self.addRules("border-bottom-left-radius: 4px;")
        self._label = paragraph(WRITING, font=theme.font(13.5),
                                colour=theme.TEXT_SECONDARY)
        self.body().addWidget(self._label)

    def setText(self, text: str) -> None:
        """Say what the companion is doing, such as which tool runs."""
        self._label.setText(text)

    def text(self) -> str:
        return self._label.text()
