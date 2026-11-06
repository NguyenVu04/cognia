"""The conversation picker on the Companion screen.

Built the way :mod:`src.ui.dialogs.tray_menu` is, and for the same reason a
native ``QMenu`` cannot carry the design's radius and drop shadow.

This control was added beyond the designed screens. It exists because
conversations now outlive the window and there has to be some way back to an
earlier one.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLayout, QVBoxLayout, QWidget

from src.domain.conversation.models import Conversation
from src.ui import theme
from src.ui.widgets.buttons import TextButton, menu_button
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.shadow import ShadowWindow
from src.ui.widgets.surface import rule
from src.ui.widgets.typography import kicker

WIDTH = 288
#: Past this, the list scrolls, so the popup never grows taller than the window.
MAX_LIST_HEIGHT = 360


class ConversationMenu(ShadowWindow):
    """Past conversations, most recent first, plus a way to start another."""

    chosen = Signal(str)  # the Conversation id
    newRequested = Signal()
    deleteRequested = Signal(str)  # the Conversation id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            radius=11,
            fill=theme.BG_CARD,
            ring=theme.BORDER,
            blur=48,
            dy=20,
            shadow_colour=theme.SHADOW.darker(),
            margin=40,
            flags=Qt.WindowType.Popup,
            parent=parent,
        )
        self.body.setFixedWidth(WIDTH)

        content = self.body.body()
        content.setContentsMargins(8, 8, 8, 8)
        content.setSpacing(0)

        heading = QWidget()
        heading_layout = QVBoxLayout(heading)
        heading_layout.setContentsMargins(12, 8, 12, 10)
        heading_layout.setSpacing(0)
        heading_layout.addWidget(kicker("Conversations", alpha=0.38, px=10.5))
        content.addWidget(heading)

        self._scroll = ScrollPane()
        self._list_layout = self._scroll.column
        content.addWidget(self._scroll)

        divider = QWidget()
        divider_layout = QVBoxLayout(divider)
        divider_layout.setContentsMargins(12, 7, 12, 7)
        divider_layout.setSpacing(0)
        divider_layout.addWidget(rule(theme.BORDER_SUBTLE))
        content.addWidget(divider)

        start = menu_button("New conversation", "chat-circle")
        start.clicked.connect(self._start)
        content.addWidget(start)

        self.layout().setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

    def setConversations(  # noqa: N802 - matches Qt naming
        self, conversations: Sequence[Conversation], current_id: str | None = None
    ) -> None:
        """Rebuild the list. The current conversation is marked, not hidden."""
        while (item := self._list_layout.takeAt(0)) is not None:
            if (widget := item.widget()) is not None:
                widget.deleteLater()

        for conversation in conversations:
            self._list_layout.addWidget(
                self._row(conversation, conversation.id == current_id)
            )
        self._scroll.refresh()
        wanted = self._list_layout.sizeHint().height()
        self._scroll.setFixedHeight(min(wanted, MAX_LIST_HEIGHT))

    def rows(self) -> int:
        """How many conversations the list holds."""
        return self._list_layout.count()

    def _row(self, conversation: Conversation, here: bool) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        button = menu_button(
            conversation.title, "check-circle" if here else "chat-circle"
        )
        button.clicked.connect(lambda _=False, i=conversation.id: self._choose(i))
        layout.addWidget(button, 1)
        delete = TextButton(
            "", font=theme.font(13), fg=theme.muted(0.45), radius=7,
            padding=(9, 10), hover_fill=theme.wash(0.12),
            hover_fg=theme.ACCENT_TEXT, icon_name="trash", icon_px=13,
        )
        delete.setToolTip("Delete conversation")
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

    def _start(self) -> None:
        self.hide()
        self.newRequested.emit()

    def popup_under(self, anchor: QPoint) -> None:
        """Show with the visible surface's top-left corner at ``anchor``.

        The window is larger than what is drawn by the transparent gutter the
        shadow is painted into, so the offset is taken from the surface.
        """
        self.adjustSize()
        self.move(anchor.x() - self.margin, anchor.y() - self.margin)
        self.show()
