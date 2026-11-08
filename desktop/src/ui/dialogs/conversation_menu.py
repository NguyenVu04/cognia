"""The conversation picker on the Companion screen."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLayout, QVBoxLayout, QWidget

from src.domain.conversation.models import Conversation
from src.ui import theme
from src.ui.widgets.buttons import Button, IconButton
from src.ui.widgets.frameless import FramelessWindow
from src.ui.widgets.layout import clear
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import rule
from src.ui.widgets.typography import kicker

WIDTH = 300
# Past this the list scrolls, so the popup never grows taller than the window.
MAX_LIST_HEIGHT = 360


class ConversationMenu(FramelessWindow):
    """Past conversations, most recent first, plus a way to start another."""

    chosen = Signal(str)
    newRequested = Signal()
    deleteRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(fill=theme.BG_CARD, flags=Qt.WindowType.Popup, parent=parent)
        self.body.setFixedWidth(WIDTH)
        content = self.body.body()
        content.setContentsMargins(8, 10, 8, 8)

        heading = QWidget()
        heading_layout = QVBoxLayout(heading)
        heading_layout.setContentsMargins(10, 0, 10, 8)
        heading_layout.addWidget(kicker("Conversations"))
        content.addWidget(heading)

        self._scroll = ScrollPane()
        self._list_layout = self._scroll.column
        self._list_layout.setSpacing(2)
        content.addWidget(self._scroll)
        content.addSpacing(6)
        content.addWidget(rule(theme.BORDER_SUBTLE))
        content.addSpacing(6)

        self.start = Button("New conversation", variant="ghost", icon_name="plus")
        self.start.setToolTip("Ctrl+N")
        self.start.clicked.connect(self._start)
        content.addWidget(self.start)
        self.layout().setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

    def setConversations(
        self, conversations: Sequence[Conversation], current_id: str | None = None
    ) -> None:
        """Rebuild the list. The current conversation is marked, not hidden."""
        clear(self._list_layout)
        for conversation in conversations:
            self._list_layout.addWidget(
                self._row(conversation, conversation.id == current_id)
            )
        self._scroll.refresh()
        wanted = self._list_layout.sizeHint().height()
        self._scroll.setFixedHeight(min(wanted, MAX_LIST_HEIGHT))

    def rows(self) -> int:
        return self._list_layout.count()

    def _row(self, conversation: Conversation, here: bool) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        button = Button(
            conversation.title,
            variant="ghost",
            icon_name="check" if here else "chat-circle",
            align_left=True,
        )
        button.clicked.connect(lambda _=False, i=conversation.id: self._choose(i))
        layout.addWidget(button, 1)
        delete = IconButton("trash", "Delete conversation", px=15, box=32)
        delete.setObjectName("delete")
        delete.clicked.connect(lambda _=False, i=conversation.id: self._delete(i))
        layout.addWidget(delete)
        return row

    def _choose(self, conversation_id: str) -> None:
        self.hide()
        self.chosen.emit(conversation_id)

    def _delete(self, conversation_id: str) -> None:
        self.hide()
        self.deleteRequested.emit(conversation_id)

    def setStartEnabled(self, enabled: bool) -> None:
        self.start.setEnabled(enabled)

    def _start(self) -> None:
        self.hide()
        self.newRequested.emit()

    def popup_under(self, anchor: QPoint) -> None:
        """Show with the top-left corner at ``anchor``."""
        self.adjustSize()
        self.move(anchor)
        self.show()
