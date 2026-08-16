"""Sessions — UC-05 and UC-07.

One line at the start, one question at the end. The open-session card and the
start-session card are alternates; only one is ever on screen.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.views import sample_data
from src.ui.widgets.buttons import accent_button, dashed_button, quiet_button
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import Panel, bottom_rule, fading_rule
from src.ui.widgets.typography import body, eyebrow, heading, kicker, label, lede

CARD_WIDTH = 660


class SessionsView(QWidget):
    nudgeRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        pane = ScrollPane(padding=(34, 40, 40, 40))
        layout.addWidget(pane)
        column = pane.column

        column.addWidget(eyebrow("UC-05 · UC-07"))
        column.addSpacing(6)
        column.addWidget(heading("Work session"))
        column.addSpacing(4)
        column.addWidget(
            lede(
                "One line at the start, one question at the end. In between "
                "the companion is quiet and still.",
                max_width=600,
            )
        )
        column.addSpacing(26)

        self.open_card = self._open_card()
        column.addWidget(self.open_card, 0, Qt.AlignmentFlag.AlignLeft)
        self.start_card = self._start_card()
        self.start_card.setVisible(False)
        column.addWidget(self.start_card, 0, Qt.AlignmentFlag.AlignLeft)

        column.addSpacing(34)
        column.addWidget(kicker("Earlier"))
        column.addSpacing(12)
        column.addWidget(self._past(), 0, Qt.AlignmentFlag.AlignLeft)

        column.addSpacing(26)
        preview = dashed_button(
            "Preview the break nudge (UC-06)", px=12.5, radius=7,
            padding=(9, 14), icon_name="coffee",
        )
        preview.clicked.connect(self.nudgeRequested)
        column.addWidget(preview, 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)

    def _open_card(self) -> Panel:
        card = Panel(
            fill=theme.BG_CARD, ring=theme.BORDER, radius=11,
            padding=(24, 26, 24, 26),
        )
        card.setFixedWidth(CARD_WIDTH)

        top = QHBoxLayout()
        top.setSpacing(20)
        left = QVBoxLayout()
        left.setSpacing(5)
        left.addWidget(kicker(sample_data.SESSION_OPENED, alpha=0.4, px=10.5))
        left.addWidget(
            label(sample_data.SESSION_INTENT, font=theme.font(19, 500),
                  colour=theme.TEXT)
        )
        top.addLayout(left)
        top.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(0)
        elapsed = label(
            sample_data.SESSION_ELAPSED,
            font=theme.font(26, 500, tabular=True), colour=theme.TEXT,
        )
        elapsed.setAlignment(Qt.AlignmentFlag.AlignRight)
        at_machine = label(
            "at the machine", font=theme.font(11.5), colour=theme.muted(0.45)
        )
        at_machine.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(elapsed)
        right.addWidget(at_machine)
        top.addLayout(right)
        card.body().addLayout(top)

        card.body().addSpacing(20)
        card.body().addWidget(fading_rule(theme.muted(0.16)))
        card.body().addSpacing(20)

        card.body().addWidget(
            body("How did that go?", px=14, alpha=0.8)
        )
        card.body().addSpacing(12)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.closing = QLineEdit()
        self.closing.setPlaceholderText("One line, or skip it")
        self.closing.setFont(theme.font(13.5))
        row.addWidget(self.closing, 1)
        close = accent_button("Close session", px=13.5, radius=8, padding=(11, 18))
        close.clicked.connect(self._close_session)
        row.addWidget(close)
        skip = quiet_button("Skip", px=13.5, radius=8, padding=(11, 16))
        skip.clicked.connect(self._close_session)
        row.addWidget(skip)
        card.body().addLayout(row)
        return card

    def _start_card(self) -> Panel:
        card = Panel(
            fill=theme.BG_CARD, ring=theme.BORDER, radius=11,
            padding=(24, 26, 24, 26),
        )
        card.setFixedWidth(CARD_WIDTH)
        card.body().addWidget(
            label("What are you working on?", font=theme.font(16, 500),
                  colour=theme.TEXT)
        )
        card.body().addSpacing(4)
        card.body().addWidget(
            label(
                "One line. You can skip it — nothing is guessed on your behalf.",
                font=theme.font(12.5), colour=theme.muted(0.5),
            )
        )
        card.body().addSpacing(16)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.intent = QLineEdit()
        self.intent.setPlaceholderText("e.g. Positioning chapter, second pass")
        self.intent.setFont(theme.font(13.5))
        row.addWidget(self.intent, 1)
        start = accent_button("Start", px=13.5, radius=8, padding=(11, 18))
        start.clicked.connect(self._start_session)
        row.addWidget(start)
        card.body().addLayout(row)
        return card

    def _past(self) -> QWidget:
        holder = QWidget()
        holder.setFixedWidth(CARD_WIDTH)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        for session in sample_data.PAST_SESSIONS:
            row_widget = bottom_rule()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(2, 13, 2, 13)
            row.setSpacing(20)

            left = QVBoxLayout()
            left.setSpacing(2)
            left.addWidget(body(session.intent, px=14))
            left.addWidget(body(session.answer, px=12, alpha=0.45))
            row.addLayout(left)
            row.addStretch(1)

            meta = label(
                f"{session.when} · {session.length}",
                font=theme.font(12.5, tabular=True), colour=theme.muted(0.55),
            )
            row.addWidget(meta, 0, Qt.AlignmentFlag.AlignTop)
            column.addWidget(row_widget)
        return holder

    # Presentational only — the cards simply swap.

    def _close_session(self) -> None:
        self.closing.clear()
        self.open_card.setVisible(False)
        self.start_card.setVisible(True)

    def _start_session(self) -> None:
        self.intent.clear()
        self.start_card.setVisible(False)
        self.open_card.setVisible(True)
