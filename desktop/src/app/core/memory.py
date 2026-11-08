"""What the companion remembers: the list, a correction, a removal, and why it
feels as it does."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.app.commands import CorrectEntry, ExplainFeeling, RemoveEntry
from src.domain.events.models import EventKind
from src.domain.memory.models import MemoryItem
from src.domain.ports import CharacterStoreFailed, EventLogFailed, MemoryStoreFailed

if TYPE_CHECKING:
    from src.app.core_host import CoreHost


class MemoryHandler:
    handles = (CorrectEntry, RemoveEntry, ExplainFeeling)

    def __init__(self, core: CoreHost) -> None:
        self.core = core

    def start(self) -> None:
        self.refresh()
        if self.core.embedding_identity is not None:
            try:
                self.core.memory.check_model(self.core.embedding_identity)
            except MemoryStoreFailed:
                pass
        self.embed_missing()

    def handle(self, item) -> None:
        match item:
            case CorrectEntry(entry, text):
                self._correct(entry, text)
            case RemoveEntry(entry):
                self._remove(entry)
            case ExplainFeeling():
                self._explain()

    def refresh(self) -> None:
        try:
            entries = self.core.memory.entries()
        except MemoryStoreFailed as error:
            self.core.bridge.memoryFailed.emit(str(error))
            return
        self.core.bridge.memoryShown.emit(entries)

    def _correct(self, entry: MemoryItem, text: str) -> None:
        try:
            self.core.memory.correct(entry, text)
        except ValueError:
            pass  # the view refuses a blank line before it gets here
        except MemoryStoreFailed as error:
            self.core.bridge.memoryFailed.emit(str(error))
            return
        self.refresh()
        self.embed_missing()

    def _remove(self, entry: MemoryItem) -> None:
        core = self.core
        try:
            with core.db.transaction():
                core.memory.remove(entry)
                result = core.record(
                    EventKind.MEMORY_REMOVED, {"memory_item_id": entry.id}
                )
        except (MemoryStoreFailed, EventLogFailed) as error:
            core.bridge.memoryFailed.emit(str(error))
            return
        core.commit(result)
        self.refresh()

    def _explain(self) -> None:
        core = self.core
        now = core.clock()
        version = core.character.version
        name = version.name if version else ""
        try:
            found = core.companion.explanation(core.state, now, now.tzinfo)
        except (CharacterStoreFailed, EventLogFailed, ValueError):
            found = None
        core.bridge.feelingExplained.emit(name, found)

    def embed_missing(self) -> None:
        try:
            missing = self.core.memory.missing_vectors()
        except MemoryStoreFailed:
            return
        if missing:
            self.core.bridge.askEmbed.emit(missing)

    def embedded(self, pairs) -> None:
        for entry, vector in pairs:
            try:
                self.core.memory.store_vector(entry, vector)
            except MemoryStoreFailed:
                return  # it waits for the next chance
