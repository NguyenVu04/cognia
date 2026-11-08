"""Erasing: everything remembered, or everything without exception. The next
step counts what goes before anything goes."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from src.domain.erasure.models import Level
from src.ui.views.settings.common import Section, setting_row
from src.ui.widgets.buttons import Button


class EraseSection(Section):
    #: The level, as the value of :class:`Level`.
    eraseRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Erase",
            "This can't be undone, so I'll show you exactly what goes before "
            "anything is erased.",
            parent,
        )
        panel = self.card()
        memory = Button("Erase memory…")
        memory.clicked.connect(lambda: self.eraseRequested.emit(Level.MEMORY.value))
        panel.body().addWidget(setting_row(
            "Everything remembered", "Everything I remember about you, and how "
            "I've felt. I'll stay me.",
            memory)[0])
        panel.body().addSpacing(14)
        everything = Button("Erase everything…", variant="danger")
        everything.clicked.connect(
            lambda: self.eraseRequested.emit(Level.EVERYTHING.value)
        )
        panel.body().addWidget(setting_row(
            "Everything without exception", "A completely fresh start, as if "
            "we'd never met.", everything)[0])
