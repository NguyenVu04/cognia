"""Said once, the first time the user closes the window: Cognia keeps running
in the tray, and Quit is there."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from src.ui.dialogs.base import DialogWindow
from src.ui.widgets.buttons import Button


class CloseNotice(DialogWindow):
    acknowledged = Signal()

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__("Still here", width=420, parent=parent)
        who = name or "Your companion"
        self.title("Cognia keeps running")
        self.text(
            f"{who} stays on the desktop and Cognia waits in the tray, next to the "
            "clock. Open it again from there. To end everything, choose Quit "
            "Cognia in the tray menu."
        )
        self.buttons.addStretch(1)
        self.add_button(Button("Got it", variant="primary"), self._ok)

    def _ok(self) -> None:
        self.close()
        self.acknowledged.emit()
