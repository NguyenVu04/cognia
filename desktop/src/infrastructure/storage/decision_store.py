"""Each decision to speak, and its figures, in the shared database."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from src.domain.ports.decision_store import DecisionStoreFailed
from src.domain.speech.models import Factor, MessageKind, Outcome
from src.infrastructure.storage import orm
from src.infrastructure.storage.database import Database
from src.infrastructure.storage.times import to_text, to_utc

decisions = orm.SpeechDecision.__table__
factors_table = orm.DecisionFactor.__table__

NOT_SAVED = "The decision to speak could not be recorded, so nothing was said."


class SqliteDecisionStore:
    """A :class:`~src.domain.ports.decision_store.DecisionStore`. Runs inside
    the caller's transaction when there is one."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def record(
        self,
        kind: MessageKind,
        trigger_seq: int | None,
        decided_at: datetime,
        outcome: Outcome,
        withheld_by: str,
        factors: Sequence[Factor],
    ) -> str:
        decision_id = uuid.uuid4().hex
        try:
            with self._db.transaction() as db:
                db.execute(insert(decisions).values(
                    id=decision_id,
                    kind=kind.value,
                    trigger_seq=trigger_seq,
                    decided_at=to_text(to_utc(decided_at)),
                    outcome=outcome.value,
                    withheld_by=withheld_by or None,
                ))
                if factors:
                    db.execute(insert(factors_table), [
                        {
                            "decision_id": decision_id,
                            "position": position,
                            "name": factor.name,
                            "value": factor.value,
                            "ref_id": factor.ref_id or None,
                            "event_seq": factor.event_seq,
                        }
                        for position, factor in enumerate(factors)
                    ])
        except SQLAlchemyError as error:
            raise DecisionStoreFailed(NOT_SAVED) from error
        return decision_id

    def respond(self, decision_id: str, response: str) -> None:
        try:
            with self._db.transaction() as db:
                db.execute(
                    update(decisions).where(decisions.c.id == decision_id)
                    .values(response=response)
                )
        except SQLAlchemyError as error:
            raise DecisionStoreFailed(NOT_SAVED) from error

    def sent_since(self, moment: datetime, kinds: Sequence[MessageKind]) -> int:
        query = select(func.count()).select_from(decisions).where(
            decisions.c.outcome == Outcome.SENT.value,
            decisions.c.decided_at >= to_text(to_utc(moment)),
            decisions.c.kind.in_([k.value for k in kinds]),
        )
        try:
            with self._db.transaction() as db:
                return int(db.execute(query).scalar() or 0)
        except SQLAlchemyError as error:
            raise DecisionStoreFailed(NOT_SAVED) from error
