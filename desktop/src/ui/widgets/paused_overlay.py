"""The paused state, over everything below the title bar."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from src.ui import icons, theme
from src.ui.widgets.buttons import Button
from src.ui.widgets.surface import StyledWidget
from src.ui.widgets.typography import label, paragraph, set_paragraph_text

BLURB_WIDTH = 440


class PausedOverlay(StyledWidget):
    resumed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = ""
        self.setRules(f"background: {theme.css(theme.OVERLAY)};")
        column = QVBoxLayout(self)
        column.addStretch(1)
        centre = QVBoxLayout()
        centre.setSpacing(0)
        centre.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        glyph = icons.icon_label("pause", 36, theme.ACCENT)
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        centre.addWidget(glyph)
        centre.addSpacing(14)
        self.title = label("Paused", font=theme.font(23, 700))
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        centre.addWidget(self.title)
        centre.addSpacing(8)
        self.blurb = paragraph(
            _blurb(""), font=theme.font(14.5), colour=theme.TEXT_SECONDARY,
            max_width=BLURB_WIDTH,
        )
        self.blurb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        centre.addWidget(self.blurb, 0, Qt.AlignmentFlag.AlignHCenter)
        centre.addSpacing(22)
        self.resume = Button("Resume now", variant="primary", icon_name="play")
        self.resume.clicked.connect(self.resumed)
        centre.addWidget(self.resume, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addLayout(centre)
        column.addStretch(1)

    def setPause(self, until_text: str) -> None:
        """Say until when, such as "until 15:40" or "until you resume"."""
        self.title.setText(f"Paused {until_text}".strip())

    def setCharacterName(self, name: str) -> None:
        self._name = name
        set_paragraph_text(
            self.blurb, _blurb(name), font=theme.font(14.5), max_width=BLURB_WIDTH
        )


def _blurb(name: str) -> str:
    who = name or "Your companion"
    return (
        f"{who} is taking a break too. Nothing is noticed or kept until you "
        "come back."
    )
