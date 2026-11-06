"""Conversation bubbles.

The companion and the user get mirrored corner radii — the square corner sits
on the side the message came from. A companion message may carry a note chip
underneath saying what was written down, which is how the design shows memory
being recorded in the open rather than behind the user's back.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from src.domain.conversation.models import Message
from src.ui import icons, theme
from src.ui.widgets.surface import Panel
from src.ui.widgets.typography import paragraph, set_paragraph_text

MAX_WIDTH = 434  # 60% of the 724px message column
WRITING = "writing…"


class MessageRow(QWidget):
    """One message, aligned to its side of the column."""

    def __init__(self, message: Message, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from_user = message.from_user

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        if from_user:
            row.addStretch(1)

        stack = QVBoxLayout()
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(7)

        bubble = Panel(
            fill=theme.wash(0.14) if from_user else theme.BG_BUBBLE,
            ring=theme.wash(0.30) if from_user else theme.BORDER,
            radius=12,
            padding=(12, 15, 12, 15),
        )
        # The square corner marks the speaker: bottom-right for the user,
        # bottom-left for the companion.
        bubble.addRules(
            "border-bottom-right-radius: 3px;" if from_user
            else "border-bottom-left-radius: 3px;"
        )
        bubble.setMaximumWidth(MAX_WIDTH)
        self._text = paragraph(
            message.text,
            font=theme.font(14),
            colour=theme.TEXT,
            line_height=1.6,
            max_width=MAX_WIDTH - 32,
        )
        bubble.body().addWidget(self._text)
        stack.addWidget(bubble)
        self._stack = stack
        self._note: _NoteChip | None = None
        self._check: _NoteChip | None = None

        if message.note:
            self.setNote(message.note)

        row.addLayout(stack)
        if not from_user:
            row.addStretch(1)

    def setText(self, text: str) -> None:  # noqa: N802 - matches Qt naming
        """Rewrite the bubble in place, for a reply arriving a piece at a time."""
        set_paragraph_text(
            self._text,
            text,
            font=theme.font(14),
            line_height=1.6,
            max_width=MAX_WIDTH - 32,
        )

    def setNote(self, text: str) -> None:  # noqa: N802 - matches Qt naming
        """Show the chip under the bubble, in place of any earlier one."""
        if self._note is not None:
            self._note.setParent(None)
            self._note.deleteLater()
        self._note = _NoteChip(text)
        self._stack.addWidget(self._note)

    def setCheck(self, text: str) -> None:  # noqa: N802 - matches Qt naming
        """Show the numbers of the reply that came from nothing it checked, with
        the figures it did find, under any note."""
        if self._check is not None:
            self._check.setParent(None)
            self._check.deleteLater()
        self._check = _NoteChip(text, icon="prohibit")
        self._stack.addWidget(self._check)

    def checkText(self) -> str:  # noqa: N802 - matches Qt naming
        return self._check.text if self._check is not None else ""


class _NoteChip(QWidget):
    """A chip under a companion message: what it stored, or what it checked."""

    def __init__(
        self, text: str, parent: QWidget | None = None, *, icon: str = "brain"
    ) -> None:
        super().__init__(parent)
        self.text = text
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        chip = Panel(
            fill=theme.wash(0.09), ring=theme.wash(0.28), radius=7,
            padding=(9, 12, 9, 12),
        )
        chip.setMaximumWidth(MAX_WIDTH)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(icons.icon_label(icon, 12, theme.ACCENT_TEXT))
        row.addWidget(
            paragraph(
                text,
                font=theme.font(12),
                colour=theme.ACCENT_TEXT,
                line_height=1.5,
                max_width=MAX_WIDTH - 60,
            ),
            1,
        )
        chip.body().addLayout(row)
        outer.addWidget(chip)
        outer.addStretch(1)


class TypingIndicator(Panel):
    """The “writing…” pill the design shows while a reply is being composed."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            fill=theme.BG_BUBBLE, ring=theme.BORDER, radius=12,
            padding=(11, 16, 11, 16), parent=parent,
        )
        self.addRules("border-bottom-left-radius: 3px;")
        self._label = paragraph(WRITING, font=theme.font(13), colour=theme.muted(0.5))
        self.body().addWidget(self._label)

    def setText(self, text: str) -> None:  # noqa: N802 - matches Qt naming
        """Say what the companion is doing, such as which tool runs."""
        self._label.setText(text)

    def text(self) -> str:
        return self._label.text()
