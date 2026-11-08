from datetime import datetime, timezone

from src.domain.speech import rules
from src.domain.speech.models import (
    Candidate,
    Factor,
    MessageKind,
    Moment,
    Outcome,
    SpeechSettings,
)
from src.domain.speech.speech_service import SpeechService

AT = datetime(2026, 11, 9, 11, 2, tzinfo=timezone.utc)
SETTINGS = SpeechSettings.defaults()


class FakeDecisions:
    def __init__(self) -> None:
        self.kept: list[tuple] = []
        self.responses: dict[str, str] = {}

    def record(
        self, kind, trigger_seq, decided_at, outcome, withheld_by, factors
    ) -> str:
        self.kept.append((kind, outcome, withheld_by, tuple(factors)))
        return f"d{len(self.kept)}"

    def respond(self, decision_id: str, response: str) -> None:
        self.responses[decision_id] = response

    def sent_since(self, moment, kinds) -> int:
        return sum(1 for k, o, _, _ in self.kept if o is Outcome.SENT and k in kinds)


def moment(**changes) -> Moment:
    values = dict(
        at=AT,
        at_desk=True,
        locked=False,
        presenting=False,
        typing=False,
        hidden=False,
        sent_today=0,
    )
    values.update(changes)
    return Moment(**values)


BREAK = Candidate(
    MessageKind.BREAK,
    3,
    (
        Factor(rules.OBSERVED_S, 5700.0),
        Factor(rules.THRESHOLD_S, 5400.0, text="user"),
        Factor(rules.MOOD, 0.0, text="calm"),
        Factor(rules.CEILING, -1.0, text="0"),
    ),
    AT,
)


def test_release_records_then_returns_the_message() -> None:
    decisions = FakeDecisions()
    service = SpeechService(decisions)

    verdict, message = service.release(
        BREAK,
        "Stretch with me? You've been here 1 hour 35 minutes.",
        moment(),
        SETTINGS,
        0.0,
    )

    assert verdict.outcome is Outcome.SENT
    assert message.decision_id == "d1"
    assert decisions.kept[0][1] is Outcome.SENT
    assert decisions.kept[0][3][-1].name == rules.TYPING_DELAY_S


def test_bad_words_fall_back_to_the_plain_words() -> None:
    service = SpeechService(FakeDecisions())

    _, message = service.release(
        BREAK, "You've been working 9 hours!", moment(), SETTINGS, 0.0
    )

    assert message.text.startswith("You've been at the machine for 1 hour 35 minutes")


def test_no_words_and_no_plain_words_withholds() -> None:
    remark = Candidate(
        MessageKind.REMARK,
        1,
        (
            Factor(rules.QUIET_MIN, 120.0),
            Factor(rules.MOOD, 0.0, text="calm"),
            Factor(rules.CEILING, -1.0, text="0"),
        ),
        AT,
    )
    decisions = FakeDecisions()

    verdict, message = SpeechService(decisions).release(
        remark, None, moment(), SETTINGS, 0.0
    )

    assert message is None
    assert verdict.withheld_by == rules.NO_WORDS


def test_release_checks_the_moment_again() -> None:
    decisions = FakeDecisions()

    verdict, message = SpeechService(decisions).release(
        BREAK, "Break?", moment(locked=True), SETTINGS, 0.0
    )

    assert message is None
    assert decisions.kept[0][2] == rules.LOCKED


def test_consider_records_a_refusal_only() -> None:
    decisions = FakeDecisions()
    service = SpeechService(decisions)

    assert service.consider(BREAK, moment(), SETTINGS).passes
    service.consider(BREAK, moment(presenting=True), SETTINGS)

    assert [k[2] for k in decisions.kept] == [rules.PRESENTING]


def test_respond_records() -> None:
    decisions = FakeDecisions()

    SpeechService(decisions).respond("d9", "postponed")

    assert decisions.responses == {"d9": "postponed"}
