"""The tray popup — UC-15.

A native ``QMenu`` cannot carry the design's 11px radius and drop shadow, so
this is a frameless popup window instead. It closes when clicked away from,
which is what ``Qt.Popup`` gives it.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QLayout, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.views import sample_data
from src.ui.widgets.buttons import menu_button
from src.ui.widgets.shadow import ShadowWindow
from src.ui.widgets.surface import rule
from src.ui.widgets.typography import kicker

WIDTH = 262


class TrayMenu(ShadowWindow):
    """Pause options, plus the two controls the sidebar also offers."""

    paused = Signal(str)  # the PauseOption id
    hideCompanionRequested = Signal()

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

        heading = kicker("Pause — UC-15", alpha=0.38, px=10.5)
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(12, 8, 12, 10)
        holder_layout.setSpacing(0)
        holder_layout.addWidget(heading)
        content.addWidget(holder)

        for option in sample_data.PAUSE_OPTIONS:
            button = menu_button(option.label, option.icon)
            button.clicked.connect(
                lambda _=False, o=option.id: self._choose(o)
            )
            content.addWidget(button)

        divider = QWidget()
        divider_layout = QVBoxLayout(divider)
        divider_layout.setContentsMargins(12, 7, 12, 7)
        divider_layout.setSpacing(0)
        divider_layout.addWidget(rule(theme.BORDER_SUBTLE))
        content.addWidget(divider)

        self.hide_button = menu_button("Hide from desktop", "eye-slash")
        self.hide_button.clicked.connect(self._hide_companion)
        content.addWidget(self.hide_button)

        close = menu_button("Close menu", "x")
        close.clicked.connect(self.hide)
        content.addWidget(close)

        self.layout().setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

    def _choose(self, option_id: str) -> None:
        self.hide()
        self.paused.emit(option_id)

    def _hide_companion(self) -> None:
        self.hide()
        self.hideCompanionRequested.emit()

    def setHideLabel(self, text: str) -> None:  # noqa: N802 - matches Qt naming
        self.hide_button.setLabel(text)

    def popup_at(self, anchor: QPoint) -> None:
        """Show with the visible surface's bottom-right corner at ``anchor``."""
        self.adjustSize()
        self.move(
            anchor.x() - self.width() + self.margin,
            anchor.y() - self.height() + self.margin,
        )
        self.show()
