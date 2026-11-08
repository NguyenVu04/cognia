from datetime import datetime, time, timezone

import pytest

from src.domain.speech import rules
from src.domain.speech.models import (
    Candidate,
    Factor,
    MessageKind,
    Moment,
    Outcome,
    SpeechSettings,
)

AT = datetime(2026, 11, 9, 11, 2, tzinfo=timezone.utc)
SETTINGS = SpeechSettings.defaults()


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


def break_candidate(*extra: Factor) -> Candidate:
    factors = (
        Factor(rules.OBSERVED_S, 10020.0),
        Factor(rules.THRESHOLD_S, 5400.0, text="user"),
        Factor(rules.MOOD, 0.4, text="lively"),
        Factor(rules.CEILING, -1.0, text="0"),
        *extra,
    )
    return Candidate(MessageKind.BREAK, 12, factors, AT)


def test_complete_candidate_passes() -> None:
    assert rules.admit(break_candidate(), moment(), SETTINGS).passes


@pytest.mark.parametrize(
    ("changes", "rule"),
    [
        ({"locked": True}, rules.LOCKED),
        ({"presenting": True}, rules.PRESENTING),
        ({"at_desk": False}, rules.AWAY),
    ],
)
def test_moment_withholds(changes, rule) -> None:
    verdict = rules.admit(break_candidate(), moment(**changes), SETTINGS)

    assert (verdict.outcome, verdict.withheld_by) == (Outcome.WITHHELD, rule)


def test_quiet_hours_across_midnight_withhold() -> None:
    settings = SpeechSettings(
        None, (time(22, 0), time(7, 0)), frozenset(MessageKind), True, None
    )
    late = moment(at=datetime(2026, 11, 9, 23, 30))

    assert (
        rules.admit(break_candidate(), late, settings).withheld_by == rules.QUIET_HOURS
    )
    assert rules.in_quiet_hours(time(6, 59), settings.quiet)
    assert not rules.in_quiet_hours(time(7, 0), settings.quiet)


def test_kind_off_withholds() -> None:
    settings = SpeechSettings(None, None, frozenset({MessageKind.REMARK}), True, None)

    assert (
        rules.admit(break_candidate(), moment(), settings).withheld_by == rules.KIND_OFF
    )


def test_ceiling_reached_withholds_but_not_greeting() -> None:
    settings = SpeechSettings(2, None, frozenset(MessageKind), True, None)
    greeting = Candidate(
        MessageKind.GREETING,
        1,
        (
            Factor(rules.NOTHING, 0.0),
            Factor(rules.MOOD, 0.0, text="calm"),
        ),
        AT,
    )

    assert (
        rules.admit(break_candidate(), moment(sent_today=2), settings).withheld_by
        == rules.CEILING_REACHED
    )
    assert rules.admit(greeting, moment(sent_today=2), settings).passes


def test_missing_factor_withholds_as_defect() -> None:
    lacking = Candidate(MessageKind.BREAK, 1, (Factor(rules.OBSERVED_S, 60.0),), AT)

    verdict = rules.admit(lacking, moment(), SETTINGS)

    assert verdict.withheld_by.startswith(rules.DEFECT)
    assert "threshold_s" in verdict.withheld_by


def test_return_needs_its_minutes_or_the_unknown_mark() -> None:
    bare = Candidate(MessageKind.RETURN, 1, (Factor(rules.MOOD, 0.0, text="calm"),), AT)

    assert "away_min" in rules.missing(bare)[0]


def test_hidden_holds() -> None:
    assert (
        rules.admit(break_candidate(), moment(hidden=True), SETTINGS).outcome
        is Outcome.HELD
    )


def test_wording_extra_number_fails() -> None:
    check = rules.check_wording(
        "You've been here for 3 hours.", break_candidate().factors
    )

    assert not check.ok
    assert "3" in check.problem


def test_wording_figures_pass() -> None:
    text = "You've been here for 2 hours 47 minutes. Your threshold is 90 minutes."

    assert rules.check_wording(text, break_candidate().factors).ok


@pytest.mark.parametrize("phrase", ["working", "behind", "you should"])
def test_wording_blame_fails(phrase: str) -> None:
    assert not rules.check_wording(f"Hey, {phrase} too long.", ()).ok


def test_break_fixed_wording_has_minutes() -> None:
    text = rules.fixed_wording(MessageKind.BREAK, break_candidate().factors)

    assert text == (
        "You've been at the machine for 2 hours 47 minutes. Time for a short break?"
    )


def test_remark_has_no_fixed_wording() -> None:
    assert rules.fixed_wording(MessageKind.REMARK, ()) is None


def test_return_after_clock_gap_states_no_minutes() -> None:
    text = rules.fixed_wording(MessageKind.RETURN, (Factor(rules.AWAY_UNKNOWN, 0.0),))

    assert text == "Welcome back. I can't tell how long you were away."


def test_reasons_lines_match_the_example() -> None:
    factors = (*break_candidate().factors, Factor(rules.TYPING_DELAY_S, 720.0))

    lines = rules.reasons(MessageKind.BREAK, factors)

    assert lines == (
        "You've been here without a break for 2 hours 47 minutes.",
        "Your break threshold: 1 hour 30 minutes.",
        "My mood: lively, so I spoke sooner.",
        "You haven't set a daily limit.",
        "I waited 12 minutes for you to stop typing.",
    )


def test_ceiling_factor_counts_use() -> None:
    settings = SpeechSettings(5, None, frozenset(MessageKind), True, None)

    factor = rules.ceiling_factor(settings, 2)

    assert rules.reasons(MessageKind.BREAK, (factor,)) == (
        "I've started 2 of my 5 chats today.",
    )


@pytest.mark.parametrize(
    ("minutes", "text"),
    [
        (0, "0 minutes"),
        (1, "1 minute"),
        (60, "1 hour"),
        (61, "1 hour 1 minute"),
        (167, "2 hours 47 minutes"),
    ],
)
def test_duration(minutes: int, text: str) -> None:
    assert rules.duration(minutes) == text
