"""Settings: one list of sections on the left, the chosen section on the right."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui import theme
from src.ui.views.settings.desk import DeskSection
from src.ui.views.settings.erase import EraseSection
from src.ui.views.settings.speaking_up import SpeakingUpSection
from src.ui.views.settings.startup import StartupSection
from src.ui.views.settings.tools import ToolsSection
from src.ui.views.settings.voice import VoiceSection
from src.ui.widgets.surface import StyledWidget

SPEAKING_UP = "speaking"
DESK = "desk"
VOICE = "voice"
TOOLS = "tools"
STARTUP = "startup"
ERASE = "erase"

_TITLES = (
    (SPEAKING_UP, "Speaking up"),
    (DESK, "Desk awareness"),
    (VOICE, "Voice"),
    (TOOLS, "Add-ons"),
    (STARTUP, "Startup"),
    (ERASE, "Erase"),
)


class SettingsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.speaking_up = SpeakingUpSection()
        self.desk = DeskSection()
        self.voice = VoiceSection()
        self.tools = ToolsSection()
        self.startup = StartupSection()
        self.erase = EraseSection()
        self._sections = {
            SPEAKING_UP: self.speaking_up,
            DESK: self.desk,
            VOICE: self.voice,
            TOOLS: self.tools,
            STARTUP: self.startup,
            ERASE: self.erase,
        }

        menu = StyledWidget()
        menu.setFixedWidth(184)
        menu.setRules(f"border-right: 1px solid {theme.css(theme.HAIRLINE)};")
        column = QVBoxLayout(menu)
        column.setContentsMargins(12, 26, 12, 12)
        column.setSpacing(2)
        self._group = QButtonGroup(self)
        self._buttons: dict[str, QPushButton] = {}
        for section_id, title in _TITLES:
            button = QPushButton(title)
            button.setCheckable(True)
            button.setFont(theme.font(13.5, 600))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton {"
                f"color: {theme.css(theme.TEXT_SECONDARY)}; text-align: left;"
                "border: 0; border-radius: 8px; padding: 8px 12px;"
                "}"
                f"QPushButton:hover {{ background: {theme.css(theme.wash(0.08))}; }}"
                "QPushButton:checked {"
                f"color: {theme.css(theme.ACCENT_TEXT)};"
                f"background: {theme.css(theme.wash(0.14))};"
                "}"
            )
            button.clicked.connect(lambda _=False, s=section_id: self.openSection(s))
            self._group.addButton(button)
            self._buttons[section_id] = button
            column.addWidget(button)
        column.addStretch(1)
        row.addWidget(menu)

        self.stack = QStackedWidget()
        for section in self._sections.values():
            self.stack.addWidget(section)
        row.addWidget(self.stack, 1)
        self.openSection(SPEAKING_UP)

    def openSection(self, section_id: str) -> None:
        self._buttons[section_id].setChecked(True)
        self.stack.setCurrentWidget(self._sections[section_id])

    def currentSection(self) -> str:
        return next(
            s for s, w in self._sections.items() if w is self.stack.currentWidget()
        )
