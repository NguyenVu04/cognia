"""The paused state.

Covers everything below the title bar. The design blurs what is behind it, but
the fill is already 92% opaque, so the blur is dropped rather than faked.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from src.ui import icons, theme
from src.ui.widgets.buttons import accent_button
from src.ui.widgets.surface import StyledWidget
from src.ui.widgets.typography import label, paragraph, set_paragraph_text

BLURB_WIDTH = 420


class PausedOverlay(StyledWidget):
    resumed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRules(f"background: {theme.css(theme.OVERLAY)};")

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addStretch(1)

        centre = QVBoxLayout()
        centre.setSpacing(0)
        centre.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        glyph = icons.icon_label("pause-circle", 34, theme.ACCENT)
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        centre.addWidget(glyph)
        centre.addSpacing(14)

        self._title = label(
            "Paused", font=theme.font(22, 500), colour=theme.TEXT
        )
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        centre.addWidget(self._title)
        centre.addSpacing(8)

        self._blurb = paragraph(
            _blurb("the companion"), font=theme.font(14), colour=theme.muted(0.55),
            line_height=1.6, max_width=BLURB_WIDTH,
        )
        self._blurb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        centre.addWidget(self._blurb, 0, Qt.AlignmentFlag.AlignHCenter)
        centre.addSpacing(22)

        resume = accent_button("Resume now", px=14, radius=8, padding=(11, 22))
        resume.clicked.connect(self.resumed)
        centre.addWidget(resume, 0, Qt.AlignmentFlag.AlignHCenter)

        column.addLayout(centre)
        column.addStretch(1)

    def setPauseLabel(self, label_text: str) -> None:  # noqa: N802 - Qt naming
        self._title.setText(f"Paused {label_text}".rstrip())

    def setCharacterName(self, name: str) -> None:  # noqa: N802 - Qt naming
        set_paragraph_text(
            self._blurb, _blurb(name or "the companion"), font=theme.font(14),
            max_width=BLURB_WIDTH,
        )


def _blurb(name: str) -> str:
    return (
        "Nothing is observed, nothing is sent, nothing is recorded for this "
        f"period, and {name} is off the screen. The gap will not be filled in "
        "afterwards."
    )
