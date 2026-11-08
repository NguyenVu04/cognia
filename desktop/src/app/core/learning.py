"""What the companion learns: new patterns as events arrive, their undo, and
marking one wrong."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from src.app.commands import MarkLearnedWrong, UndoLearned
from src.domain.events.models import Event, EventKind
from src.domain.initiative.models import Learned as Timing
from src.domain.learning import rules
from src.domain.learning.models import Learned, LearningState
from src.domain.ports import EventLogFailed
from src.domain.ports.pattern_store import PatternStoreFailed
from src.domain.speech import rules as speech
from src.domain.speech.models import Candidate, Factor, MessageKind

if TYPE_CHECKING:
    from src.app.core_host import CoreHost


class LearningHandler:
    handles = (UndoLearned, MarkLearnedWrong)

    def __init__(self, core: CoreHost) -> None:
        self.core = core
        self.state = LearningState()
        self.rejected: set[tuple[str, tuple[int, ...]]] = set()
        self.learned: list[Learned] = []

    def fold(self, events: Iterable[Event]) -> None:
        self.state = LearningState()
        self.rejected = set()
        for event in events:
            self._count(event)
        self._read()

    def _count(self, event: Event) -> None:
        if event.kind == EventKind.PATTERN_REJECTED:
            evidence = tuple(int(s) for s in event.payload.get("evidence", ()))
            self.rejected.add((str(event.payload.get("fingerprint", "")), evidence))
        self.state = rules.observe(self.state, event)

    def _read(self) -> None:
        try:
            self.learned = self.core.patterns.all()
        except PatternStoreFailed:
            self.learned = []

    def show(self) -> None:
        self._read()
        self.core.bridge.learnedShown.emit(list(self.learned))

    def active(self) -> list:
        """The patterns in force: not undone."""
        return [x.pattern for x in self.learned if not x.undone]

    def timing(self) -> Timing:
        patterns = self.active()
        return Timing(rules.frequency(patterns), rules.absence_hours(patterns))

    def wants_short_replies(self) -> bool:
        return rules.wants_short_replies(self.active())

    def observe(self, event: Event) -> None:
        """Count the event, and keep any pattern it completes."""
        self._count(event)
        known = {x.pattern.fingerprint for x in self.learned}
        for pattern in rules.find_patterns(self.state, known, self.rejected):
            self._keep(pattern)

    def _keep(self, pattern) -> None:
        core = self.core
        changes = rules.adjustments_for(pattern)
        now = core.clock()
        try:
            with core.db.transaction():
                learned = core.patterns.add(pattern, changes, now)
                found = core.record(
                    EventKind.PATTERN_FOUND,
                    {"pattern_id": learned.id, "fingerprint": pattern.fingerprint},
                    now,
                )
        except (PatternStoreFailed, EventLogFailed, ValueError):
            return
        self.learned.insert(0, learned)
        core.commit(found)
        self.core.bridge.learnedShown.emit(list(self.learned))
        core.proactive.consider(Candidate(
            MessageKind.ADJUSTMENT,
            found.event.seq if found.event else None,
            (
                Factor(speech.PATTERN, float(len(pattern.evidence)),
                       ref_id=learned.id, text=pattern.statement),
                Factor(speech.ADJUSTMENT, 0.0, text=rules.describe(pattern)),
            ),
            now,
        ))

    def handle(self, item) -> None:
        match item:
            case UndoLearned(learned_id):
                self.undo(learned_id)
            case MarkLearnedWrong(learned_id):
                self._mark_wrong(learned_id)

    def undo(self, learned_id: str) -> None:
        core = self.core
        try:
            with core.db.transaction():
                learned = core.patterns.undo(learned_id, core.clock())
                result = core.record(
                    EventKind.ADJUSTMENT_UNDONE, {"pattern_id": learned_id}
                )
        except (PatternStoreFailed, EventLogFailed, ValueError) as error:
            core.bridge.noticeShown.emit(str(error))
            return
        if learned is not None:
            core.commit(result)
        self.show()

    def _mark_wrong(self, learned_id: str) -> None:
        """Undo the changes, keep a tombstone of the conclusion, and forget it."""
        core = self.core
        try:
            with core.db.transaction():
                learned = core.patterns.remove(learned_id)
                if learned is None:
                    return
                pattern = learned.pattern
                result = core.record(
                    EventKind.PATTERN_REJECTED,
                    {"fingerprint": pattern.fingerprint,
                     "evidence": list(pattern.evidence)},
                )
        except (PatternStoreFailed, EventLogFailed, ValueError) as error:
            core.bridge.noticeShown.emit(str(error))
            return
        core.commit(result)
        self.show()
