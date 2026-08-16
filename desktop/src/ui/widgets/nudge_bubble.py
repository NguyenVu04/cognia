"""The break nudge, and the explanation behind it — UC-06 and UC-17.

The "Why did this appear?" panel is the point of the component: the real
figures the decision was made from, not a description of the feature. A
message whose explanation cannot be assembled is never sent (NFR-10).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.views import sample_data
from src.ui.widgets.buttons import accent_button, quiet_button
from src.ui.widgets.surface import Panel
from src.ui.widgets.typography import kicker, paragraph

WIDTH = 320


class NudgeBubble(Panel):
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            fill=theme.BG_BUBBLE, ring=theme.BORDER, radius=12,
            padding=(16, 18, 16, 18), parent=parent,
        )
        self.setFixedWidth(WIDTH)
        self.addRules("border-bottom-left-radius: 3px;")

        self.body().addWidget(
            paragraph(
                sample_data.NUDGE_TEXT, font=theme.font(13.8),
                colour=theme.TEXT, line_height=1.6, max_width=WIDTH - 38,
            )
        )

        self._why = self._why_panel()
        self._why.setVisible(False)
        self.body().addSpacing(12)
        self.body().addWidget(self._why)

        self.body().addSpacing(14)
        # The design wraps this row (``flex-wrap: wrap``) because the three
        # captions do not fit across 320px. Qt has no wrapping box layout, so
        # the break is made explicit: two buttons, then the explanation.
        actions = QVBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(7)

        first = QHBoxLayout()
        first.setSpacing(7)
        take = accent_button("Take one", px=12.5, weight=400, radius=7,
                             padding=(7, 13))
        take.clicked.connect(self.dismissed)
        first.addWidget(take)

        later = quiet_button("Later", px=12.5, radius=7, padding=(7, 13))
        later.clicked.connect(self.dismissed)
        first.addWidget(later)
        first.addStretch(1)
        actions.addLayout(first)

        second = QHBoxLayout()
        second.setSpacing(7)
        self._why_button = quiet_button(
            "Why did this appear?", px=12.5, radius=7, padding=(7, 13)
        )
        self._why_button.clicked.connect(self._toggle_why)
        second.addWidget(self._why_button)
        second.addStretch(1)
        actions.addLayout(second)
        self.body().addLayout(actions)

    def _why_panel(self) -> Panel:
        panel = Panel(
            fill=theme.wash(0.08), ring=theme.wash(0.24), radius=8,
            padding=(12, 14, 12, 14),
        )
        panel.body().addWidget(kicker("Why this appeared · UC-17", alpha=0.4, px=10.5))
        panel.body().addSpacing(6)
        for line in sample_data.NUDGE_WHY:
            panel.body().addWidget(
                paragraph(
                    line, font=theme.font(12), colour=theme.ACCENT_TEXT,
                    line_height=1.7, max_width=WIDTH - 66,
                )
            )
        return panel

    def _toggle_why(self) -> None:
        showing = not self._why.isVisible()
        self._why.setVisible(showing)
        self._why_button.setLabel(
            "Hide the reason" if showing else "Why did this appear?"
        )
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            parent.adjustSize()

    def reset(self) -> None:
        """Collapse the explanation, as re-showing the nudge does."""
        self._why.setVisible(False)
        self._why_button.setLabel("Why did this appear?")
