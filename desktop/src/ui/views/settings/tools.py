"""Add-ons: the tool servers the user added. None by default; each can be
removed."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from src.domain.tools.models.tool_server import STDIO, ToolServer
from src.ui import theme
from src.ui.views.settings.common import Section
from src.ui.widgets.buttons import Button
from src.ui.widgets.layout import clear
from src.ui.widgets.typography import body, caption


class ToolsSection(Section):
    addRequested = Signal()
    removeRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Add-ons",
            "I already have handy tools like a calculator and a dictionary. "
            "Add-ons give me more, but they come from elsewhere and may send what "
            "you ask them over the internet.",
            parent,
        )
        panel = self.card()
        self.rows = QVBoxLayout()
        self.rows.setSpacing(8)
        panel.body().addLayout(self.rows)
        add = Button("Add an add-on", variant="primary", icon_name="plus")
        add.clicked.connect(self.addRequested)
        self.column.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)
        self.setServers(())

    def setServers(self, servers: Sequence[ToolServer]) -> None:
        clear(self.rows)
        if not servers:
            self.rows.addWidget(caption("No add-ons yet — you don't need any.", px=13))
        for server in servers:
            self.rows.addWidget(self._row(server))

    def _row(self, server: ToolServer) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(body(server.name, weight=700))
        where = " ".join((server.command, *server.args)) if server.transport == STDIO \
            else server.url
        text.addWidget(body(where, px=12.5, colour=theme.TEXT_SECONDARY))
        layout.addLayout(text, 1)
        remove = Button("Remove", size="small", variant="danger")
        remove.clicked.connect(lambda: self.removeRequested.emit(server.id))
        layout.addWidget(remove)
        return row
