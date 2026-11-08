"""The patterns the companion learned, in the shared database."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from src.domain.learning.models import Adjustment, Learned, Pattern
from src.domain.ports.pattern_store import PatternStoreFailed
from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.times import to_text

patterns = orm.Pattern.__table__
evidence = orm.PatternEvidence.__table__
adjustments = orm.SelfAdjustment.__table__

NOT_READ = "What I learned could not be read."
NOT_SAVED = "What I learned could not be changed. Nothing was changed."


class SqlitePatternStore:
    """A :class:`~src.domain.ports.pattern_store.PatternStore`. Runs inside the
    caller's transaction when there is one."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def add(
        self, pattern: Pattern, changes: Sequence[Adjustment], at: datetime
    ) -> Learned:
        learned_id = uuid.uuid4().hex
        try:
            with self._db.transaction() as db:
                db.execute(insert(patterns).values(
                    id=learned_id,
                    rule_id=pattern.rule_id,
                    parameters=json.dumps(dict(pattern.parameters)),
                    statement=pattern.statement,
                    fingerprint=pattern.fingerprint,
                    found_at=to_text(at),
                ))
                db.execute(insert(evidence), [
                    {"pattern_id": learned_id, "event_seq": seq}
                    for seq in pattern.evidence
                ])
                if changes:
                    db.execute(insert(adjustments), [
                        {
                            "id": uuid.uuid4().hex,
                            "pattern_id": learned_id,
                            "aspect": change.aspect,
                            "value_before": change.value_before,
                            "value_after": change.value_after,
                            "applied_at": to_text(at),
                        }
                        for change in changes
                    ])
        except SQLAlchemyError as error:
            raise PatternStoreFailed(NOT_SAVED) from error
        return Learned(learned_id, pattern, tuple(changes), at)

    def all(self) -> list[Learned]:
        try:
            with self._db.transaction() as db:
                rows = db.execute(
                    select(patterns).order_by(patterns.c.found_at.desc())
                ).all()
                return [self._learned(db, row) for row in rows]
        except SQLAlchemyError as error:
            raise PatternStoreFailed(NOT_READ) from error

    def undo(self, learned_id: str, at: datetime) -> Learned | None:
        try:
            with self._db.transaction() as db:
                db.execute(
                    update(adjustments)
                    .where(adjustments.c.pattern_id == learned_id,
                           adjustments.c.undone_at.is_(None))
                    .values(undone_at=to_text(at))
                )
                return self._one(db, learned_id)
        except SQLAlchemyError as error:
            raise PatternStoreFailed(NOT_SAVED) from error

    def remove(self, learned_id: str) -> Learned | None:
        try:
            with self._db.transaction() as db:
                learned = self._one(db, learned_id)
                db.execute(delete(patterns).where(patterns.c.id == learned_id))
                return learned
        except SQLAlchemyError as error:
            raise PatternStoreFailed(NOT_SAVED) from error

    def _one(self, db, learned_id: str) -> Learned | None:
        row = db.execute(select(patterns).where(patterns.c.id == learned_id)).first()
        return self._learned(db, row) if row else None

    @staticmethod
    def _learned(db, row) -> Learned:
        seqs = db.execute(
            select(evidence.c.event_seq)
            .where(evidence.c.pattern_id == row.id)
            .order_by(evidence.c.event_seq)
        ).scalars().all()
        changes = db.execute(
            select(adjustments).where(adjustments.c.pattern_id == row.id)
        ).all()
        parameters = tuple(sorted(json.loads(row.parameters).items()))
        pattern = Pattern(row.rule_id, parameters, tuple(seqs), row.statement)
        return Learned(
            id=row.id,
            pattern=pattern,
            adjustments=tuple(
                Adjustment(c.aspect, c.value_before, c.value_after) for c in changes
            ),
            found_at=datetime.fromisoformat(row.found_at),
            undone=bool(changes) and all(c.undone_at for c in changes),
        )
