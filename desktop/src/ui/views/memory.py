"""Memory — UC-12, UC-13, UC-14.

Two groups: what the user said, and what the companion noticed. Nothing
appears in the second column without the evidence printed under it, and the
erase strip states the count before anything goes.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from src.ui import theme
from src.ui.views import sample_data
from src.ui.widgets.buttons import accent_button, quiet_button, small_button
from src.ui.widgets.scroll import ScrollPane
from src.ui.widgets.surface import Panel, StyledWidget
from src.ui.widgets.typography import body, eyebrow, heading, kicker, lede, paragraph

# max-width: 900px in the design, but the content column is only this wide.
COLUMNS_WIDTH = 716
COLUMN_WIDTH = (COLUMNS_WIDTH - 26) // 2


class MemoryItemCard(Panel):
    """One remembered item, with an inline edit field behind an Edit button."""

    def __init__(
        self,
        item: sample_data.MemoryItem,
        *,
        remove_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            fill=theme.BG_CARD, ring=theme.BORDER_SUBTLE, radius=9,
            padding=(14, 16, 14, 16), parent=parent,
        )
        self._item = item

        self.view = paragraph(
            item.text, font=theme.font(13.8), colour=theme.TEXT,
            line_height=1.55, fill=True,
        )
        self.body().addWidget(self.view)

        self.edit = QLineEdit(item.text)
        self.edit.setFont(theme.font(13.5))
        self.edit.setStyleSheet(
            "QLineEdit {"
            f"border-radius: 6px; padding: 7px 9px;"
            f"border: 1px solid {theme.css(theme.ACCENT)};"
            "}"
        )
        self.edit.setVisible(False)
        self.body().addWidget(self.edit)

        if item.evidence:
            self.body().addSpacing(9)
            evidence = StyledWidget()
            evidence.setRules(
                f"border-left: 2px solid {theme.css(theme.wash(0.5))};"
            )
            holder = QVBoxLayout(evidence)
            holder.setContentsMargins(11, 0, 0, 0)
            holder.setSpacing(0)
            holder.addWidget(
                paragraph(
                    item.evidence, font=theme.font(12),
                    colour=theme.muted(0.5), line_height=1.5, fill=True,
                )
            )
            self.body().addWidget(evidence)

        self.body().addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(body(item.date, px=11.5, alpha=0.4))
        row.addStretch(1)
        self.edit_button = small_button("Edit")
        self.edit_button.clicked.connect(self._toggle_edit)
        row.addWidget(self.edit_button)
        row.addWidget(small_button(remove_label))
        self.body().addLayout(row)

    def _toggle_edit(self) -> None:
        editing = not self.edit.isVisible()
        self.edit.setVisible(editing)
        self.view.setVisible(not editing)
        self.edit_button.setLabel("Done" if editing else "Edit")
        if editing:
            self.edit.setFocus()
        else:
            self.view.setText(self.edit.text())


class MemoryView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        pane = ScrollPane(padding=(34, 40, 40, 40))
        layout.addWidget(pane)
        column = pane.column

        column.addWidget(eyebrow("UC-12 · UC-13 · UC-14"))
        column.addSpacing(6)
        column.addWidget(heading("What I remember"))
        column.addSpacing(4)
        column.addWidget(
            lede(
                "Everything held about you, on your disk. Two groups: what you "
                "told me, and what I noticed — and nothing appears in the "
                "second without the evidence under it.",
                max_width=600,
            )
        )
        column.addSpacing(26)
        column.addWidget(self._columns(), 0, Qt.AlignmentFlag.AlignLeft)
        column.addSpacing(32)
        column.addWidget(self._erase_strip(), 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)

    def _columns(self) -> QWidget:
        holder = QWidget()
        holder.setFixedWidth(COLUMNS_WIDTH)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(26)
        row.addWidget(self._group("You told me", sample_data.TOLD, "Delete"))
        row.addWidget(self._group("I noticed", sample_data.NOTICED, "Wrong"))
        return holder

    def _group(
        self, title: str, items: list[sample_data.MemoryItem], remove_label: str
    ) -> QWidget:
        group = QWidget()
        group.setFixedWidth(COLUMN_WIDTH)
        column = QVBoxLayout(group)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(kicker(title))
        column.addSpacing(12)
        for item in items:
            column.addWidget(MemoryItemCard(item, remove_label=remove_label))
            column.addSpacing(10)
        column.addStretch(1)
        return group

    def _erase_strip(self) -> Panel:
        count = len(sample_data.TOLD) + len(sample_data.NOTICED)
        strip = Panel(
            fill=theme.wash(0.06), ring=theme.wash(0.22), radius=10,
            padding=(16, 20, 16, 20),
        )
        strip.setFixedWidth(COLUMNS_WIDTH)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(
            paragraph(
                f"Erase everything remembered ({count} items) and keep "
                f"{sample_data.CHARACTERS[0].name} — or erase without "
                "exception. You are told the count before anything goes.",
                font=theme.font(13), colour=theme.muted(0.7), line_height=1.55,
                fill=True,
            ),
            1,
        )
        row.addWidget(
            quiet_button("Erase memory", px=12.5, radius=7, padding=(9, 14),
                         fg=theme.muted(0.75))
        )
        row.addWidget(
            accent_button("Erase everything", px=12.5, weight=400, radius=7,
                          padding=(9, 14))
        )
        strip.body().addLayout(row)
        return strip
