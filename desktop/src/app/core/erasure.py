"""Erasing: the count before, and what is left after."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.app.commands import Erase, PreviewErasure
from src.domain.erasure.models import Level
from src.domain.events.models import EventKind
from src.domain.ports import ErasureFailed

if TYPE_CHECKING:
    from src.app.core_host import CoreHost


class ErasureHandler:
    handles = (PreviewErasure, Erase)

    def __init__(self, core: CoreHost) -> None:
        self.core = core

    def handle(self, item) -> None:
        match item:
            case PreviewErasure(level):
                self._preview(level)
            case Erase(level):
                self._erase(level)

    def _preview(self, level: Level) -> None:
        core = self.core
        try:
            counts = core.erasure.preview(level)
        except ErasureFailed as error:
            core.bridge.memoryFailed.emit(str(error))
            return
        version = core.character.version
        core.bridge.erasurePreviewed.emit(
            level, counts, version.name if version else None
        )

    def _erase(self, level: Level) -> None:
        core = self.core
        core.chat.abandon()
        report = core.erasure.erase(level)
        core.bridge.erasureReported.emit(report)
        self._after()

    def _after(self) -> None:
        """Show what is left. The feelings start again at the resting mood of the
        character that remains, if one does."""
        core = self.core
        core.fold()
        core.character.load()
        version = core.character.version
        if version is not None:
            core.record_now(EventKind.CHARACTER_CHANGED, {"version_id": version.id})
        core.chat.after_erasure()
        core.memory_handler.refresh()
        core.learning.show()
        # Erasing everything returns the settings to their defaults.
        core.desk.start()
        core.settings_handler.start()
        core.proactive.start()
        core.show_feeling(force=True)
