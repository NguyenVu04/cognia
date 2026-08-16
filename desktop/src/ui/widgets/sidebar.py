"""The 214px navigation rail.

Wordmark and the local-only line at the top, the six destinations in the
middle, and — pinned to the bottom — the session status card and the pause
control that the tray also offers, because the companion is never the only
route to anything (FR-28).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.ui import icons, theme
from src.ui.views import sample_data
from src.ui.widgets.buttons import LayoutButton, quiet_button
from src.ui.widgets.surface import Panel, StyledWidget
from src.ui.widgets.typography import kicker, label

WIDTH = 214


class NavButton(LayoutButton):
    """One destination. Selected state changes fill, colour and weight."""

    def __init__(self, item: sample_data.NavItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 9, 10, 9)
        row.setSpacing(10)
        self._icon = icons.icon_label(item.icon, 16, theme.muted(0.62))
        self._text = QLabel(item.label)
        self._text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self._icon)
        row.addWidget(self._text)
        row.addStretch(1)

        self.setActive(False)

    def setActive(self, active: bool) -> None:  # noqa: N802 - matches Qt naming
        self.setChecked(active)
        fill = theme.wash(0.12) if active else None
        fg = theme.ACCENT_TEXT if active else theme.muted(0.62)
        self.setStyleSheet(
            "QPushButton {"
            f"border: 0; border-radius: 7px;"
            f"background: {theme.css(fill) if fill else 'transparent'};"
            "}"
            "QPushButton:hover {"
            f"background: {theme.css(theme.wash(0.12 if active else 0.06))};"
            "}"
        )
        self._text.setFont(theme.font(13.5, 500 if active else 400))
        self._text.setStyleSheet(
            f"color: {theme.css(fg)}; background: transparent;"
        )
        self._icon.setStyleSheet(
            f"color: {theme.css(fg)}; background: transparent;"
        )


class Sidebar(StyledWidget):
    navigated = Signal(str)
    pauseRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(WIDTH)
        self.setRules(
            f"background: {theme.css(theme.BG_SIDEBAR)};"
            f"border-right: 1px solid {theme.css(theme.BORDER_SUBTLE)};"
        )

        column = QVBoxLayout(self)
        column.setContentsMargins(12, 20, 12, 14)
        column.setSpacing(0)

        # Wordmark block: padding 0 10px 20px.
        header = QVBoxLayout()
        header.setContentsMargins(10, 0, 10, 20)
        header.setSpacing(3)
        header.addWidget(
            label("Cognia", font=theme.font(17, 500, spacing_em=-0.01),
                  colour=theme.TEXT)
        )
        local = QHBoxLayout()
        local.setSpacing(5)
        local.addWidget(icons.icon_label("hard-drives", 11, theme.muted(0.4)))
        local.addWidget(
            label("local only", font=theme.font(11), colour=theme.muted(0.4))
        )
        local.addStretch(1)
        header.addLayout(local)
        column.addLayout(header)

        nav = QVBoxLayout()
        nav.setSpacing(2)
        self._buttons: list[NavButton] = []
        for item in sample_data.NAV:
            button = NavButton(item)
            button.clicked.connect(
                lambda _=False, i=item.id: self.navigated.emit(i)
            )
            nav.addWidget(button)
            self._buttons.append(button)
        column.addLayout(nav)

        column.addStretch(1)

        footer = QVBoxLayout()
        footer.setSpacing(10)

        status = Panel(
            fill=theme.BG_INSET, ring=theme.BORDER_SUBTLE, radius=8,
            padding=(11, 12, 11, 12),
        )
        status.body().setSpacing(3)
        status.body().addWidget(kicker("Session open", alpha=0.38, px=10.5))
        status.body().addWidget(
            label(sample_data.SESSION_INTENT, font=theme.font(13),
                  colour=theme.muted(0.85), wrap=True)
        )
        footer.addWidget(status)

        pause = quiet_button(
            "Pause…", px=13, radius=7, padding=(9, 12),
            fg=theme.muted(0.7), icon_name="pause",
        )
        pause.clicked.connect(self.pauseRequested)
        footer.addWidget(pause)
        column.addLayout(footer)

    def setCurrent(self, screen_id: str) -> None:  # noqa: N802 - matches Qt naming
        for button in self._buttons:
            button.setActive(button.item.id == screen_id)
