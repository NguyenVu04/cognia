"""Companion — the conversation screen.

The default destination. Header, the message column, and a composer that never
takes focus away from anything else.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.views import sample_data
from src.ui.widgets.buttons import accent_button, quiet_button
from src.ui.widgets.message_bubble import MessageRow, TypingIndicator
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import StyledWidget, bottom_rule
from src.ui.widgets.typography import label


class ChatView(QWidget):
    hideCompanionRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        character = sample_data.CHARACTERS[0]

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

        self.hide_button = quiet_button(
            "Hide from desktop", px=12.5, radius=7, padding=(8, 13),
            fg=theme.muted(0.72), icon_name="eye-slash", gap=7,
        )
        self.hide_button.clicked.connect(self.hideCompanionRequested)
        row.addWidget(self.hide_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    def _messages(self) -> QWidget:
        pane = ScrollPane(padding=(26, 36, 26, 36), spacing=16)
        for message in sample_data.MESSAGES:
            pane.column.addWidget(MessageRow(message))

        typing = QHBoxLayout()
        typing.setContentsMargins(0, 0, 0, 0)
        typing.addWidget(TypingIndicator())
        typing.addStretch(1)
        self.typing_row = QWidget()
        self.typing_row.setLayout(typing)
        self.typing_row.setVisible(False)  # shown only while a reply is composed
        pane.column.addWidget(self.typing_row)

        pane.column.addStretch(1)
        return pane

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
        row.addWidget(self.draft, 1)

        self.send = accent_button(
            "Send", px=14, radius=9, padding=(13, 20),
            icon_name="paper-plane-right",
        )
        row.addWidget(self.send)
        return bar

    def setHideLabel(self, text: str) -> None:  # noqa: N802 - matches Qt naming
        """Track whether the companion is on screen, as the tray does."""
        self.hide_button.setLabel(text)
