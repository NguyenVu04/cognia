"""The navigation rail.

The destinations at the top; at the bottom the controls the tray also offers
— pause, show or hide the companion — and the state of the model, because the
companion on the desktop is never the only route to anything.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from src.ui import icons, theme
from src.ui.views.navigation import NAV_ITEMS, NavItem
from src.ui.widgets.buttons import Button
from src.ui.widgets.surface import StyledWidget
from src.ui.widgets.typography import caption, label

WIDTH = 210

LOADING = "loading"
READY = "ready"
UNAVAILABLE = "unavailable"
_STATE_TEXT = {
    LOADING: "Waking up…",
    READY: "Ready to talk",
    UNAVAILABLE: "Can't think right now",
}


class NavButton(QPushButton):
    """One destination. The checked one is the screen on view."""

    def __init__(self, item: NavItem, parent: QWidget | None = None) -> None:
        super().__init__(item.label, parent)
        self.item = item
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(theme.font(14, 600))
        self.setToolTip(f"{item.label} ({item.shortcut})")
        glyph = QIcon()
        for state, colour in (
            (QIcon.State.Off, theme.TEXT_SECONDARY),
            (QIcon.State.On, theme.ACCENT_TEXT),
        ):
            glyph.addPixmap(
                icons.icon(item.icon, 17, colour).pixmap(17, 17),
                QIcon.Mode.Normal,
                state,
            )
        self.setIcon(glyph)
        self.setIconSize(QSize(17, 17))
        self.setStyleSheet(
            "QPushButton {"
            f"color: {theme.css(theme.TEXT_SECONDARY)}; text-align: left;"
            "border: 0; border-radius: 9px; padding: 9px 12px; background: transparent;"
            "}"
            f"QPushButton:hover {{ background: {theme.css(theme.wash(0.08))}; }}"
            "QPushButton:checked {"
            f"color: {theme.css(theme.ACCENT_TEXT)};"
            f"background: {theme.css(theme.wash(0.16))};"
            "}"
            f"QPushButton:focus {{ outline: none; border: 1px solid "
            f"{theme.css(theme.ACCENT_2)}; }}"
        )


class ModelStatus(QWidget):
    """A dot, a line about the model, and Retry when it cannot run."""

    retryRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 0, 10, 0)
        column.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._dot = StyledWidget()
        self._dot.setFixedSize(8, 8)
        row.addWidget(self._dot)
        self.text = caption("")
        self.text.setWordWrap(True)
        row.addWidget(self.text, 1)
        column.addLayout(row)
        self.retry = Button("Try again", size="small", icon_name="arrows-clockwise")
        self.retry.clicked.connect(self.retryRequested)
        column.addWidget(self.retry, 0, Qt.AlignmentFlag.AlignLeft)
        self.setState(LOADING, "")

    def setState(self, state: str, detail: str) -> None:
        """``loading``, ``ready`` or ``unavailable``. ``detail``, such as the
        GPU or why the model cannot run, shows in the tooltip."""
        colour = {
            LOADING: theme.ACCENT_2,
            READY: theme.SUCCESS,
            UNAVAILABLE: theme.DANGER,
        }[state]
        self._dot.setRules(f"background: {theme.css(colour)}; border-radius: 4px;")
        self.text.setText(_STATE_TEXT[state])
        self.text.setToolTip(detail or _STATE_TEXT[state])
        self.retry.setVisible(state == UNAVAILABLE)


class Sidebar(StyledWidget):
    navigated = Signal(str)
    pauseRequested = Signal()
    resumeRequested = Signal()
    companionToggled = Signal()
    retryRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paused = False
        self.setFixedWidth(WIDTH)
        self.setRules(
            f"background: {theme.css(theme.BG_SIDEBAR)};"
            f"border-right: 1px solid {theme.css(theme.BORDER_SUBTLE)};"
        )
        column = QVBoxLayout(self)
        column.setContentsMargins(12, 18, 12, 14)
        column.setSpacing(2)

        header = QVBoxLayout()
        header.setContentsMargins(10, 0, 10, 16)
        header.setSpacing(2)
        header.addWidget(label("Cognia", font=theme.font(18, 800)))
        header.addWidget(caption("Here with you"))
        column.addLayout(header)

        self._buttons: list[NavButton] = []
        for item in NAV_ITEMS:
            button = NavButton(item)
            button.clicked.connect(lambda _=False, i=item.id: self.navigated.emit(i))
            column.addWidget(button)
            self._buttons.append(button)
        column.addStretch(1)

        self.companion = Button(
            "Hide companion", variant="ghost", icon_name="eye-slash", align_left=True
        )
        self.companion.clicked.connect(self.companionToggled)
        column.addWidget(self.companion)
        self.pause = Button(
            "Pause…", variant="ghost", icon_name="pause", align_left=True
        )
        self.pause.clicked.connect(self._pause_clicked)
        column.addWidget(self.pause)
        column.addSpacing(12)
        self.model = ModelStatus()
        self.model.retryRequested.connect(self.retryRequested)
        column.addWidget(self.model)

    def setCurrent(self, screen_id: str) -> None:
        for button in self._buttons:
            button.setChecked(button.item.id == screen_id)

    def current(self) -> str:
        return next((b.item.id for b in self._buttons if b.isChecked()), "")

    def setPaused(self, paused: bool) -> None:
        self._paused = paused
        self.pause.setText("Resume" if paused else "Pause…")
        self.pause.setIcon(
            icons.icon("play" if paused else "pause", 16, theme.TEXT_SECONDARY)
        )

    def setCompanionHidden(self, hidden: bool, name: str) -> None:
        who = name or "companion"
        self.companion.setText(f"Show {who}" if hidden else f"Hide {who}")
        self.companion.setIcon(
            icons.icon("eye" if hidden else "eye-slash", 16, theme.TEXT_SECONDARY)
        )

    def setModelState(self, state: str, detail: str = "") -> None:
        self.model.setState(state, detail)

    def _pause_clicked(self) -> None:
        if self._paused:
            self.resumeRequested.emit()
        else:
            self.pauseRequested.emit()
