"""Erasing at the two levels above the single item."""

from __future__ import annotations

from src.domain.erasure import rules
from src.domain.erasure.models import ErasureReport, GroupCount, Level
from src.domain.ports import ErasureFailed, ErasureStore


class ErasureService:
    """Counts before anything goes, then erases group by group.

    A group that fails does not stop the others, so as much as possible is
    removed and the report says exactly what remains. Running it again removes
    what is left.
    """

    def __init__(self, store: ErasureStore) -> None:
        self._store = store

    def preview(self, level: Level) -> tuple[GroupCount, ...]:
        """The rows each group holds. Raises ``ErasureFailed`` if they cannot be
        counted."""
        return tuple(GroupCount(g, self._store.count(g)) for g in rules.groups(level))

    def erase(self, level: Level) -> ErasureReport:
        erased, failed = [], []
        for group in rules.groups(level):
            try:
                self._store.erase(group)
            except ErasureFailed:
                failed.append(group)
            else:
                erased.append(group)
        try:
            self._store.compact()
            compacted = True
        except ErasureFailed:
            compacted = False
        return ErasureReport(tuple(erased), tuple(failed), compacted)
