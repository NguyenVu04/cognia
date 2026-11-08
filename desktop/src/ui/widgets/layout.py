"""Small helpers that several views share for their layouts."""

from __future__ import annotations

from PySide6.QtWidgets import QLayout, QWidget


def clear(layout: QLayout) -> None:
    """Remove and delete every widget and nested layout in ``layout``."""
    while layout.count():
        item = layout.takeAt(0)
        if (widget := item.widget()) is not None:
            # Hidden but still a child until deleted: a widget with no parent
            # would become a window of its own.
            widget.hide()
            widget.deleteLater()
        elif (inner := item.layout()) is not None:
            clear(inner)


def centre_on(widget: QWidget, parent: QWidget) -> None:
    """Move a top-level ``widget`` to the centre of ``parent`` on screen."""
    centre = parent.mapToGlobal(parent.rect().center())
    widget.move(centre.x() - widget.width() // 2, centre.y() - widget.height() // 2)
