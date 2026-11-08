"""Adding a tool server. The user must agree that it can send data off the
machine before it is added, so nothing reaches it without that agreement."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QLineEdit, QWidget

from src.domain.tools.models.tool_server import HTTP, STDIO
from src.ui import theme
from src.ui.dialogs.base import DialogWindow
from src.ui.widgets.buttons import Button
from src.ui.widgets.dropdown import Dropdown
from src.ui.widgets.typography import caption

CONSENT = (
    "I understand this add-on isn't part of Cognia and may send what I ask it "
    "over the internet."
)


@dataclass(frozen=True)
class ServerDraft:
    """What the user typed. ``args`` are split on spaces."""

    name: str
    transport: str
    command: str
    args: tuple[str, ...]
    url: str


class AddToolServerDialog(DialogWindow):
    added = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Add an add-on", width=480, parent=parent)
        self.title("Add an add-on")
        self.text(
            "An add-on gives me new tools, like searching your notes. Only "
            "add one you trust."
        )
        self.name = self._field("Name, such as notes")
        self.transport = Dropdown()
        self.transport.addItem("A command on this computer", STDIO)
        self.transport.addItem("An address on the network", HTTP)
        self.transport.currentIndexChanged.connect(self._update)
        self.content.addWidget(self.transport)
        self.content.addSpacing(8)
        self.command = self._field(
            "Command, such as uvx my-notes-server --dir C:/notes"
        )
        self.url = self._field("Address, such as http://127.0.0.1:8000/mcp")
        self.consent = QCheckBox(CONSENT)
        self.consent.setFont(theme.font(13))
        self.consent.toggled.connect(self._update)
        self.content.addWidget(self.consent)
        self.content.addSpacing(4)
        self.content.addWidget(caption("You can remove it at any time in Settings."))
        self.buttons.addStretch(1)
        self.add_button(Button("Cancel"), self.close)
        self.add = self.add_button(Button("Add", variant="primary"), self._add)
        for field in (self.name, self.command, self.url):
            field.textChanged.connect(self._update)
        self._update()

    def _field(self, placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setFont(theme.font(13.5))
        self.content.addWidget(field)
        self.content.addSpacing(8)
        return field

    def draft(self) -> ServerDraft:
        words = self.command.text().split()
        return ServerDraft(
            name=self.name.text().strip(),
            transport=self.transport.currentData(),
            command=words[0] if words else "",
            args=tuple(words[1:]),
            url=self.url.text().strip(),
        )

    def _update(self) -> None:
        stdio = self.transport.currentData() == STDIO
        self.command.setVisible(stdio)
        self.url.setVisible(not stdio)
        draft = self.draft()
        reachable = (
            bool(draft.command)
            if stdio
            else draft.url.startswith(("http://", "https://"))
        )
        self.add.setEnabled(bool(draft.name) and reachable and self.consent.isChecked())

    def _add(self) -> None:
        self.added.emit(self.draft())
        self.close()
