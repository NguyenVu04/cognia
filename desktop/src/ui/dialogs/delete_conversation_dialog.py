"""Confirming the deletion of one conversation.

The count comes first, because deletion cannot be undone, and the lines the
user told in that conversation go with it.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from src.ui import theme
from src.ui.dialogs.base import DialogWindow
from src.ui.widgets.buttons import Button


def deletion_text(title: str, messages: int, lines: int) -> str:
    """What deleting the conversation ``title`` removes."""
    noun = "message" if messages == 1 else "messages"
    held = f"“{title}” has {messages} {noun}."
    if lines == 0:
        return f"{held} Nothing I remember comes from it."
    if lines == 1:
        return f"{held} 1 line I remember comes from it, and it goes too."
    return f"{held} {lines} lines I remember come from it, and they go too."


class DeleteConversationDialog(DialogWindow):
    confirmed = Signal()

    def __init__(
        self, title: str, messages: int, lines: int, parent: QWidget | None = None
    ) -> None:
        super().__init__("Delete conversation", width=420, parent=parent)
        self.title("Delete this conversation?")
        self.summary = deletion_text(title, messages, lines)
        self.text(self.summary)
        self.text("This cannot be undone.", colour=theme.DANGER)
        self.buttons.addStretch(1)
        self.add_button(Button("Cancel"), self.close)
        self.delete = self.add_button(Button("Delete", variant="danger"), self._confirm)

    def _confirm(self) -> None:
        self.close()
        self.confirmed.emit()
