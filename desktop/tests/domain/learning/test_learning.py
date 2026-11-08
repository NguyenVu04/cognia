from datetime import datetime, timedelta, timezone

import pytest

from src.domain.events.models import Event, EventKind
from src.domain.learning import rules
from src.domain.learning.models import (
    PASSED_OVER_KIND,
    REGULAR_ABSENCE,
    SHORT_MESSAGES,
    LearningState,
    Pattern,
)

T0 = datetime(2026, 11, 2, 11, 5, tzinfo=timezone.utc)


def event(seq: int, event_kind: EventKind, at: datetime = T0, **payload) -> Event:
    return Event(seq, at, 0, event_kind, payload, None)


def fold(*events: Event) -> LearningState:
    state = LearningState()
    for item in events:
        state = rules.observe(state, item)
    return state


def passed(seq: int, at_desk: bool = True) -> Event:
    return event(seq, EventKind.MESSAGE_PASSED_OVER, kind="remark", at_desk=at_desk)


def test_pattern_needs_evidence() -> None:
    with pytest.raises(ValueError):
        Pattern(SHORT_MESSAGES, (), (), "")


def test_three_passed_over_at_desk_finds_pattern() -> None:
    state = fold(passed(4), passed(7), passed(9))

    (pattern,) = rules.find_patterns(state, (), ())

    assert pattern.rule_id == PASSED_OVER_KIND
    assert pattern.evidence == (4, 7, 9)
    assert pattern.statement == "You let my last 3 remarks pass."
    assert rules.frequency([pattern]) == {"remark": rules.FREQUENCY_FACTOR}


def test_passed_over_away_not_counted() -> None:
    state = fold(passed(4), passed(7, at_desk=False), passed(9))

    assert rules.find_patterns(state, (), ()) == ()


def test_answer_resets_the_streak() -> None:
    state = fold(passed(4), passed(7),
                 event(8, EventKind.MESSAGE_ANSWERED, kind="remark"), passed(9))

    assert rules.find_patterns(state, (), ()) == ()


def absence(seq: int, day: int) -> tuple[Event, Event]:
    left = T0 + timedelta(days=day)
    return (
        event(seq, EventKind.PRESENCE, left, at_desk=False, idle_seconds=0),
        event(seq + 1, EventKind.PRESENCE, left + timedelta(minutes=45), at_desk=True),
    )


def test_regular_absence_three_of_seven_days() -> None:
    state = fold(*absence(10, 0), *absence(20, 1), *absence(30, 3))

    (pattern,) = rules.find_patterns(state, (), ())

    assert pattern.rule_id == REGULAR_ABSENCE
    assert pattern.parameter("hour") == "11"
    assert rules.absence_hours([pattern]) == frozenset({11})


def test_short_absences_do_not_count() -> None:
    left = T0
    short = (
        event(1, EventKind.PRESENCE, left, at_desk=False, idle_seconds=0),
        event(2, EventKind.PRESENCE, left + timedelta(minutes=5), at_desk=True),
    )

    assert fold(*short).absences == {}


def test_short_messages_median() -> None:
    events = [event(i, EventKind.USER_MESSAGE, chars=20) for i in range(1, 21)]

    (pattern,) = rules.find_patterns(fold(*events), (), ())

    assert pattern.rule_id == SHORT_MESSAGES
    assert rules.wants_short_replies([pattern])


def test_long_messages_find_nothing() -> None:
    events = [event(i, EventKind.USER_MESSAGE, chars=120) for i in range(1, 21)]

    assert rules.find_patterns(fold(*events), (), ()) == ()


def test_known_fingerprint_not_found_again() -> None:
    state = fold(passed(4), passed(7), passed(9))

    assert rules.find_patterns(state, {"passed_over_kind|kind=remark"}, ()) == ()


def test_tombstone_same_evidence_refused() -> None:
    state = fold(passed(4), passed(7), passed(9))
    tomb = ("passed_over_kind|kind=remark", (4, 7, 9))

    assert rules.find_patterns(state, (), {tomb}) == ()


def test_tombstone_new_evidence_allowed() -> None:
    state = fold(passed(14), passed(17), passed(19))
    tomb = ("passed_over_kind|kind=remark", (4, 7, 9))

    assert len(rules.find_patterns(state, (), {tomb})) == 1


def test_fingerprint_stable_order() -> None:
    a = Pattern("r", (("b", "2"), ("a", "1")), (1,), "")
    b = Pattern("r", (("a", "1"), ("b", "2")), (1,), "")

    assert a.fingerprint == b.fingerprint == "r|a=1,b=2"


def test_each_pattern_changes_one_aspect() -> None:
    state = fold(passed(4), passed(7), passed(9))
    (pattern,) = rules.find_patterns(state, (), ())

    (change,) = rules.adjustments_for(pattern)

    assert change.aspect == "frequency"
    assert rules.describe(pattern) == "I'll send remarks less often"
