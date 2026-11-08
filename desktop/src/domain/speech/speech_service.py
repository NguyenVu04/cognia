"""The SpeechGate: the one way out for everything the companion says on its own.

Each decision is recorded with its figures before anything reaches the screen,
so every message that appears can be explained, and every message that did not
appear can say which rule stopped it.
"""

from __future__ import annotations

from datetime import datetime

from src.domain.ports.decision_store import DecisionStore
from src.domain.speech import rules
from src.domain.speech.models import (
    Candidate,
    Factor,
    MessageKind,
    Moment,
    Outcome,
    ProactiveMessage,
    SpeechSettings,
    Verdict,
)

COUNTED = tuple(kind for kind in MessageKind if kind is not MessageKind.GREETING)


class SpeechService:
    """Exceptions from the store pass through unchanged."""

    def __init__(self, decisions: DecisionStore) -> None:
        self._decisions = decisions

    def sent_since(self, moment: datetime) -> int:
        """Messages that count against the daily limit, since ``moment``."""
        return self._decisions.sent_since(moment, COUNTED)

    def consider(
        self, candidate: Candidate, moment: Moment, settings: SpeechSettings
    ) -> Verdict:
        """Whether the candidate may wait for a pause. A refusal is recorded."""
        verdict = rules.admit(candidate, moment, settings)
        if verdict.outcome is Outcome.WITHHELD:
            self._record(candidate, moment.at, verdict, candidate.factors)
        return verdict

    def drop(self, candidate: Candidate, at: datetime, reason: str) -> None:
        """The reason to speak lapsed while the message waited."""
        self._record(candidate, at, Verdict(Outcome.DROPPED, reason), candidate.factors)

    def release(
        self,
        candidate: Candidate,
        words: str | None,
        moment: Moment,
        settings: SpeechSettings,
        typing_delay_s: float,
    ) -> tuple[Verdict, ProactiveMessage | None]:
        """Check the moment again, check the words, record the decision, and
        return the message to show. ``words`` is ``None`` when the model could
        not word it; the plain words of the kind are used then, if it has any.
        """
        factors = (*candidate.factors, Factor(rules.TYPING_DELAY_S, typing_delay_s))
        verdict = rules.admit(candidate, moment, settings)
        if verdict.outcome is not None:
            self._record(candidate, moment.at, verdict, factors)
            return verdict, None
        text = words
        if text is None or not rules.check_wording(text, factors).ok:
            text = rules.fixed_wording(candidate.kind, factors)
        if text is None:
            withheld = Verdict(Outcome.WITHHELD, rules.NO_WORDS)
            self._record(candidate, moment.at, withheld, factors)
            return withheld, None
        sent = Verdict(Outcome.SENT)
        decision_id = self._record(candidate, moment.at, sent, factors)
        ref = next((f.ref_id for f in factors if f.name == rules.PATTERN), "")
        message = ProactiveMessage(
            decision_id=decision_id,
            kind=candidate.kind,
            text=text,
            reasons=rules.reasons(candidate.kind, factors),
            shown_at=moment.at,
            ref_id=ref,
        )
        return sent, message

    def respond(self, decision_id: str, response: str) -> None:
        self._decisions.respond(decision_id, response)

    def _record(
        self, candidate: Candidate, at: datetime, verdict: Verdict, factors
    ) -> str:
        return self._decisions.record(
            candidate.kind,
            candidate.trigger_seq,
            at,
            verdict.outcome or Outcome.SENT,
            verdict.withheld_by,
            factors,
        )
