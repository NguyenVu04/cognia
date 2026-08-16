"""Scrolling panes for the design's ``overflow: auto`` regions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget


class ScrollPane(QScrollArea):
    """A vertical scroll area whose contents are :attr:`content`.

    ``padding`` is applied inside the scrolling region, matching the design,
    where the padding scrolls with the content rather than framing it.
    """

    def __init__(
        self,
        *,
        padding: tuple[int, int, int, int] = (0, 0, 0, 0),
        spacing: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.content = QWidget()
        self.content.setStyleSheet("background: transparent;")
        top, right, bottom, left = padding
        self.column = QVBoxLayout(self.content)
        self.column.setContentsMargins(left, top, right, bottom)
        self.column.setSpacing(spacing)
        self.setWidget(self.content)

    def _sync_height(self) -> None:
        """Scroll rather than squeeze when the content is taller than the box.

        ``setWidgetResizable`` shrinks the content down to its *minimum* when
        the viewport is smaller, which compresses every child instead of
        scrolling. CSS ``overflow: auto`` keeps the natural height, so the
        minimum is pinned to the layout's preferred height.
        """
        wanted = self.column.sizeHint().height()
        if self.content.minimumHeight() != wanted:
            self.content.setMinimumHeight(wanted)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._sync_height()
        super().resizeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._sync_height()
        super().showEvent(event)
