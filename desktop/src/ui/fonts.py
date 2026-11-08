"""Registering the vendored typefaces with Qt.

Nunito (SIL Open Font License 1.1, one variable file that holds every
weight) and Phosphor Icons (MIT) ship in ``src/resources/fonts/`` with their
licences beside them. A file that fails to load raises: a substituted face
changes every measurement and would look like a layout bug.
"""

from __future__ import annotations

from PySide6.QtGui import QFontDatabase

from src.utils.paths import resource

FILES = ("Nunito[wght].ttf", "Phosphor.ttf")


def load() -> None:
    """Register every vendored font, or raise saying which one failed."""
    for name in FILES:
        path = resource("fonts", name)
        if QFontDatabase.addApplicationFont(str(path)) == -1:
            raise RuntimeError(f"Qt refused to load the font {path}")
