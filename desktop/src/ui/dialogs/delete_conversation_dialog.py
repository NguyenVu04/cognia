"""Confirming the deletion of one conversation.

The count comes first, because deletion cannot be undone, and the lines the
user told in that conversation go with it.

This dialog was added beyond the designed screens: the design has no way to
delete a conversation.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.widgets.buttons import accent_button, quiet_button
from src.ui.widgets.shadow import ShadowWindow
from src.ui.widgets.typography import label, paragraph

WIDTH = 420
TEXT_WIDTH = WIDTH - 56


def deletion_text(title: str, messages: int, lines: int) -> str:
    """What deleting the conversation ``title`` removes."""
    noun = "message" if messages == 1 else "messages"
    held = f"“{title}” has {messages} {noun}."
    if lines == 0:
        return f"{held} Nothing I remember comes from it."
    if lines == 1:
        return f"{held} 1 line I remember comes from it, and it goes too."
    return f"{held} {lines} lines I remember come from it, and they go too."


class DeleteConversationDialog(ShadowWindow):
    confirmed = Signal()

    def __init__(
        self, title: str, messages: int, lines: int, parent: QWidget | None = None
    ) -> None:
        super().__init__(
            radius=12, fill=theme.BG_CARD, ring=theme.BORDER, blur=48, dy=20,
            shadow_colour=theme.SHADOW.darker(), margin=40,
            flags=Qt.WindowType.Dialog, parent=parent,
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("Delete conversation")
        self.body.setFixedWidth(WIDTH)

        frame = self.body.body()
        frame.setContentsMargins(28, 24, 28, 22)
        frame.setSpacing(0)
        content = QVBoxLayout()
        content.setSpacing(0)
        frame.addLayout(content)

        content.addWidget(
            label(
                "Delete this conversation?", font=theme.font(18, 500),
                colour=theme.TEXT,
            )
        )
        content.addSpacing(8)
        self.text = deletion_text(title, messages, lines)
        for text in (self.text, "This cannot be undone."):
            content.addWidget(
                paragraph(
                    text, font=theme.font(13.5), colour=theme.muted(0.7),
                    line_height=1.55, max_width=TEXT_WIDTH,
                )
            )
            content.addSpacing(6)

        frame.addSpacing(20)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        cancel = quiet_button("Cancel")
        cancel.clicked.connect(self.close)
        buttons.addWidget(cancel)
        self.delete = accent_button("Delete")
        self.delete.clicked.connect(self._confirm)
        buttons.addWidget(self.delete)
        frame.addLayout(buttons)

    def _confirm(self) -> None:
        self.close()
        self.confirmed.emit()

    def centre_on(self, widget: QWidget) -> None:
        """Place the dialog over the middle of ``widget``."""
        self.adjustSize()
        centre = widget.mapToGlobal(widget.rect().center())
        self.move(centre - self.rect().center())
