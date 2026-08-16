"""Character — UC-02 and UC-03.

The character in the words it was written in, and every earlier version kept
beside it, because a rewrite is not always an improvement.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QTextEdit, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.views import sample_data
from src.ui.widgets.buttons import accent_button, dashed_button, quiet_button, small_button
from src.ui.widgets.hatch import HatchPanel
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import Panel, bottom_rule
from src.ui.widgets.typography import body, eyebrow, heading, kicker, label, lede


class CharacterView(QWidget):
    firstRunRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        pane = ScrollPane(padding=(34, 40, 40, 40))
        layout.addWidget(pane)
        column = pane.column

        column.addWidget(eyebrow("UC-02 · UC-03"))
        column.addSpacing(6)
        column.addWidget(heading("Character"))
        column.addSpacing(4)
        column.addWidget(
            lede(
                "In force from the next message. Every earlier version is "
                "kept, appearance included — a rewrite is not always an "
                "improvement.",
                max_width=600,
            )
        )
        column.addSpacing(26)

        split = QHBoxLayout()
        split.setSpacing(26)
        split.addWidget(self._appearance(), 0, Qt.AlignmentFlag.AlignTop)
        split.addWidget(self._editor(), 1)
        holder = QWidget()
        holder.setFixedWidth(716)  # max-width: 920px, capped by the column
        holder.setLayout(split)
        column.addWidget(holder, 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)

    def _appearance(self) -> Panel:
        card = Panel(
            fill=theme.BG_CARD, ring=theme.BORDER_SUBTLE, radius=10,
            padding=(14, 14, 14, 14),
        )
        card.setFixedWidth(200)
        sprite = HatchPanel("appearance\nplaceholder", radius=7)
        sprite.setFixedHeight(180)
        card.body().addWidget(sprite)
        card.body().addSpacing(12)
        character = sample_data.CHARACTERS[0]
        card.body().addWidget(
            label(character.name, font=theme.font(15, 500), colour=theme.TEXT)
        )
        card.body().addWidget(
            label(character.role, font=theme.font(12.5), colour=theme.muted(0.5))
        )
        return card

    def _editor(self) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        column.addWidget(
            body("The character, in the words it was written in", px=13, weight=500)
        )
        column.addSpacing(8)

        editor = QTextEdit(sample_data.CHARACTER_TEXT)
        editor.setFont(theme.font(13.5))
        editor.setFixedHeight(150)
        editor.setStyleSheet("QTextEdit { border-radius: 9px; padding: 13px 15px; }")
        column.addWidget(editor)
        column.addSpacing(12)

        # The design puts these three on one row under a 920px max-width, but
        # the column only ever resolves to 716px here, so the row overflows by
        # about 10px and clips the last caption. Wrapping keeps every label
        # readable and changes nothing else.
        actions = QVBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)

        first = QHBoxLayout()
        first.setSpacing(10)
        first.addWidget(accent_button("Save", px=13.5, radius=8, padding=(10, 18)))
        first.addWidget(
            quiet_button("Hear a sample first", px=13.5, radius=8, padding=(10, 16))
        )
        first.addStretch(1)
        actions.addLayout(first)

        second = QHBoxLayout()
        second.setSpacing(10)
        open_first_run = dashed_button(
            "Open the first-run choice (UC-01)", px=13.5, radius=8, padding=(10, 16)
        )
        open_first_run.clicked.connect(self.firstRunRequested)
        second.addWidget(open_first_run)
        second.addStretch(1)
        actions.addLayout(second)
        column.addLayout(actions)

        column.addSpacing(26)
        column.addWidget(kicker("Earlier versions"))
        column.addSpacing(10)
        for version in sample_data.CHARACTER_VERSIONS:
            column.addWidget(self._version_row(version))
        return holder

    def _version_row(self, version: sample_data.CharacterVersion) -> QWidget:
        widget = bottom_rule()
        row = QHBoxLayout(widget)
        row.setContentsMargins(2, 11, 2, 11)
        row.setSpacing(14)
        row.addWidget(body(version.summary, px=13.5, alpha=0.8))
        row.addStretch(1)
        row.addWidget(body(version.date, px=12, alpha=0.42))
        row.addWidget(small_button("Restore", padding=(5, 10)))
        return widget
