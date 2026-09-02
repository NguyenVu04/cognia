"""The conversation picker on the Companion screen.

Built the way :mod:`src.ui.dialogs.tray_menu` is, and for the same reason a
native ``QMenu`` cannot carry the design's radius and drop shadow.

This control is not in the design document. It exists because conversations now
outlive the window and there has to be some way back to an earlier one; ADR
0002 records the decision.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QLayout, QVBoxLayout, QWidget

from src.core.models import Conversation
from src.ui import theme
from src.ui.widgets.buttons import menu_button
from src.ui.widgets.shadow import ShadowWindow
from src.ui.widgets.surface import rule
from src.ui.widgets.typography import kicker

WIDTH = 288
#: Enough to find your way back without growing a popup taller than the window.
MOST_RECENT = 10


class ConversationMenu(ShadowWindow):
    """Past conversations, most recent first, plus a way to start another."""

    chosen = Signal(str)  # the Conversation id
    newRequested = Signal()

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

        self._list = QWidget()
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        content.addWidget(self._list)

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

        for conversation in list(conversations)[:MOST_RECENT]:
            here = conversation.id == current_id
            button = menu_button(
                conversation.title, "check-circle" if here else "chat-circle"
            )
            button.clicked.connect(
                lambda _=False, i=conversation.id: self._choose(i)
            )
            self._list_layout.addWidget(button)

    def _choose(self, conversation_id: str) -> None:
        self.hide()
        self.chosen.emit(conversation_id)

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
