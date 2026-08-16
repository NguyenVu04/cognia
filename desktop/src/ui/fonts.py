"""Registering the vendored typefaces with Qt.

Inter (SIL Open Font License 1.1) and Phosphor Icons (MIT) ship in
``src/resources/fonts/`` with their licences alongside. Loading fails loudly:
a silently substituted face would change every measurement in the design and
look like a layout bug rather than a missing file.
"""

from __future__ import annotations

from PySide6.QtGui import QFontDatabase

from src.utils.paths import resource

_FILES = (
    "Inter-Regular.ttf",
    "Inter-Medium.ttf",
    "Inter-SemiBold.ttf",
    "Inter-Bold.ttf",
    "Phosphor.ttf",
)


def load() -> None:
    """Register every vendored font, or raise saying which one failed."""
    for name in _FILES:
        path = resource("fonts", name)
        if QFontDatabase.addApplicationFont(str(path)) == -1:
            raise RuntimeError(f"Qt refused to load the font {path}")
