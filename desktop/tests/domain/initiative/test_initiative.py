from datetime import date, datetime, timedelta, timezone

from src.domain.events.models import Event, EventKind
from src.domain.initiative import rules
from src.domain.initiative.models import (
    ACTIVE,
    AWAY,
    BREAK,
    DOZE,
    DOZING,
    TALK,
    Context,
    InitiativeState,
    Learned,
)
from src.domain.speech import rules as speech
from src.domain.speech.models import MessageKind

T0 = datetime(2026, 11, 9, 9, 15, tzinfo=timezone.utc)
CTX = Context("calm", 0.0, None, Learned(), (("q1", "What do you do for fun?"),))


def event(seq: int, event_kind: EventKind, at: datetime, **payload) -> Event:
    return Event(seq, at, 0, event_kind, payload, None)


def here(seq: int, at: datetime) -> Event:
    return event(
        seq,
        EventKind.PRESENCE,
        at,
        at_desk=True,
        locked=False,
        presenting=False,
        idle_seconds=0,
        first=False,
    )


def gone(seq: int, at: datetime, idle: int = 300) -> Event:
    return event(
        seq,
        EventKind.PRESENCE,
        at,
        at_desk=False,
        locked=False,
        presenting=False,
        idle_seconds=idle,
        first=False,
    )


def arrived(ctx: Context = CTX) -> InitiativeState:
    return rules.step(InitiativeState(), here(1, T0), ctx).state


def test_waits_replay_the_same_for_the_same_seq() -> None:
    assert rules.t_talk(1041, "calm") == rules.t_talk(1041, "calm")
    assert timedelta(minutes=90) <= rules.t_talk(1041, "calm") <= timedelta(minutes=180)


def test_lively_speaks_sooner() -> None:
    assert rules.t_talk(7, "lively") < rules.t_talk(7, "calm") < rules.t_talk(7, "low")


def test_user_threshold_replaces_the_random_break() -> None:
    assert rules.t_break(5, 90) == timedelta(minutes=90)
    assert timedelta(minutes=75) <= rules.t_break(5, None) <= timedelta(minutes=110)


def test_arrival_plans_a_break_and_a_talk() -> None:
    state = arrived()

    assert state.desk == ACTIVE
    assert state.break_at == T0 + rules.t_break(1, None)
    assert state.talk_at is not None
    assert rules.next_wake(state) == min(state.break_at, state.talk_at)


def test_away_drops_waiting_and_sets_doze() -> None:
    step = rules.step(arrived(), gone(2, T0 + timedelta(minutes=10)), CTX)

    assert step.state.desk == AWAY
    assert step.lapse == "away"
    assert step.ambient == "waiting"
    assert step.state.away_since == T0 + timedelta(minutes=5)
    assert step.state.doze_at == T0 + timedelta(minutes=35)
    assert step.state.break_at is None


def test_doze_after_thirty_minutes() -> None:
    state = rules.step(arrived(), gone(2, T0 + timedelta(minutes=10)), CTX).state

    step = rules.step(
        state, event(3, EventKind.TIMER, state.doze_at, purposes=[DOZE]), CTX
    )

    assert step.state.desk == DOZING
    assert step.ambient == DOZING


def test_return_after_twenty_minutes_with_minutes() -> None:
    state = rules.step(arrived(), gone(2, T0 + timedelta(minutes=10)), CTX).state

    step = rules.step(state, here(3, T0 + timedelta(minutes=45)), CTX)

    (candidate,) = step.candidates
    assert candidate.kind is MessageKind.RETURN
    assert candidate.factor(speech.AWAY_MIN).value == 40


def test_return_after_clock_gap_states_no_minutes() -> None:
    state = rules.step(
        arrived(), event(2, EventKind.CLOCK_GAP, T0, seconds=3600), CTX
    ).state

    step = rules.step(state, here(3, T0 + timedelta(minutes=30)), CTX)

    assert step.candidates[0].factor(speech.AWAY_UNKNOWN) is not None


def test_short_absence_keeps_the_run() -> None:
    state = rules.step(
        arrived(), gone(2, T0 + timedelta(minutes=10), idle=10), CTX
    ).state

    after = rules.step(state, here(3, T0 + timedelta(minutes=12)), CTX).state

    assert after.run_start_at == T0
    assert rules.step(state, here(3, T0 + timedelta(minutes=12)), CTX).candidates == ()


def test_break_reset_after_five_minutes_away() -> None:
    state = rules.step(arrived(), gone(2, T0 + timedelta(minutes=10)), CTX).state

    after = rules.step(state, here(3, T0 + timedelta(minutes=20)), CTX).state

    assert after.run_start_at == T0 + timedelta(minutes=20)


def test_break_timer_gives_a_break_candidate() -> None:
    state = arrived()

    step = rules.step(
        state, event(5, EventKind.TIMER, state.break_at, purposes=[BREAK]), CTX
    )

    (candidate,) = step.candidates
    assert candidate.kind is MessageKind.BREAK
    assert (
        candidate.factor(speech.OBSERVED_S).value
        == (state.break_at - T0).total_seconds()
    )
    assert candidate.factor(speech.THRESHOLD_S).text == "chosen"


def test_postpone_sets_twenty_minutes_and_counts() -> None:
    at = T0 + timedelta(hours=2)
    answer = event(
        6, EventKind.MESSAGE_ANSWERED, at, kind="break", response="postponed"
    )

    state = rules.step(arrived(), answer, CTX).state

    assert state.break_at == at + rules.POSTPONE
    assert state.postponed_breaks == 1


def test_third_postpone_offers_the_threshold() -> None:
    state = arrived()
    for seq in (6, 7, 8):
        answer = event(
            seq, EventKind.MESSAGE_ANSWERED, T0, kind="break", response="postponed"
        )
        state = rules.step(state, answer, CTX).state

    step = rules.step(
        state, event(9, EventKind.TIMER, state.break_at, purposes=[BREAK]), CTX
    )

    assert step.candidates[0].factor("postponed_count").value == 3


def test_not_today_silences_breaks() -> None:
    at = T0 + timedelta(hours=2)
    state = rules.step(
        arrived(),
        event(6, EventKind.MESSAGE_ANSWERED, at, kind="break", response="silenced"),
        CTX,
    ).state
    state = rules.step(state, here(7, at), CTX).state

    step = rules.step(state, event(8, EventKind.TIMER, at, purposes=[BREAK]), CTX)

    assert step.candidates == ()


def test_talk_timer_asks_one_question_a_day() -> None:
    state = arrived()
    first = rules.step(
        state, event(5, EventKind.TIMER, state.talk_at, purposes=[TALK]), CTX
    )
    later = first.state.talk_at or state.talk_at + timedelta(hours=3)
    second = rules.step(
        first.state, event(6, EventKind.TIMER, later, purposes=[TALK]), CTX
    )

    assert first.candidates[0].kind is MessageKind.QUESTION
    assert second.candidates[0].kind is MessageKind.REMARK


def test_never_repeat_a_question() -> None:
    state = InitiativeState(asked=frozenset({"q1"}))

    assert rules.next_question(state, CTX.questions, T0) is None


def test_paused_drops_everything() -> None:
    step = rules.step(arrived(), event(3, EventKind.PAUSED, T0), CTX)

    assert step.lapse == "paused"
    assert rules.next_wake(step.state) is None


def test_user_message_plans_the_next_talk() -> None:
    at = T0 + timedelta(minutes=30)

    state = rules.step(arrived(), event(4, EventKind.USER_MESSAGE, at), CTX).state

    assert state.talk_at == at + rules.t_talk(4, "calm")


def test_regular_absence_moves_a_plan_out_of_the_half_hour_before() -> None:
    ctx = Context("calm", 0.0, 90, Learned(absence_hours=frozenset({10})), ())

    state = rules.step(InitiativeState(), here(1, T0), ctx).state

    assert state.break_at == T0.replace(hour=10, minute=45)
    assert rules._avoid(T0.replace(hour=9, minute=40), frozenset({10})) == T0.replace(
        hour=10, minute=0
    )


def test_first_opening_before_four_is_the_day_before() -> None:
    late = datetime(2026, 11, 10, 3, 30, tzinfo=timezone.utc)

    assert not rules.first_opening(date(2026, 11, 9), late)
    assert rules.first_opening(date(2026, 11, 9), late + timedelta(hours=1))


def test_greeting_once_a_day_mentions_the_told_line() -> None:
    opened = event(1, EventKind.WINDOW_OPENED, T0)

    state, candidate = rules.greeting(
        InitiativeState(), opened, ("m1", "Has a cat"), CTX
    )
    again, none = rules.greeting(
        state, event(2, EventKind.WINDOW_OPENED, T0), None, CTX
    )

    assert candidate.factor(speech.TOLD_LINE).text == "Has a cat"
    assert none is None
    assert again.greeted_on == date(2026, 11, 9)


def test_due_names_the_timers() -> None:
    state = InitiativeState(talk_at=T0, break_at=T0 + timedelta(hours=1))

    assert rules.due(state, T0) == (TALK,)
