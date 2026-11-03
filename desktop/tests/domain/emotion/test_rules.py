from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.emotion import rules
from src.domain.emotion.models import EmotionState, Pad, Temperament
from src.domain.events.models import Event, EventKind, Payload

MONDAY = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
REST = Pad(0.10, 0.0, 0.0)
TEMPERAMENT = Temperament(0.4, 30.0, 720.0, REST)
ZERO = Pad(0.0, 0.0, 0.0)
PRAISE = Pad(0.50, 0.20, 0.10)
IGNORED = Pad(-0.30, 0.0, 0.0)


def _axes(point: Pad) -> tuple[float, float, float]:
    return (point.pleasure, point.arousal, point.dominance)


def _event(
    kind: EventKind, payload: Payload | None = None, at: datetime = MONDAY, seq: int = 1
) -> Event:
    return Event(seq, at, 0, kind, payload or {}, None)


def _state(
    mood: Pad = REST, feeling: Pad = ZERO, ignored_loss: float = 0.0
) -> EmotionState:
    return EmotionState(mood, feeling, 0, MONDAY, ignored_loss)


def test_at_rest() -> None:
    state = rules.at_rest(TEMPERAMENT, MONDAY, 0)

    assert state == EmotionState(REST, ZERO, 0, MONDAY, 0.0, False)


def test_decay_feeling_half_life() -> None:
    state = rules.decay(_state(feeling=PRAISE), TEMPERAMENT, 30)

    assert _axes(state.feeling) == pytest.approx((0.25, 0.10, 0.05))


def test_decay_mood_half_life() -> None:
    state = rules.decay(_state(mood=Pad(0.30, 0.08, 0.04)), TEMPERAMENT, 720)

    assert _axes(state.mood) == pytest.approx((0.20, 0.04, 0.02))


def test_decay_ignored_loss() -> None:
    state = rules.decay(_state(ignored_loss=0.40), TEMPERAMENT, 720)

    assert state.ignored_loss == pytest.approx(0.20)


def test_decay_zero_minutes() -> None:
    before = _state(mood=Pad(0.30, 0.08, 0.04), feeling=PRAISE, ignored_loss=0.12)

    after = rules.decay(before, TEMPERAMENT, 0)

    assert _axes(after.mood) == pytest.approx(_axes(before.mood))
    assert _axes(after.feeling) == pytest.approx(_axes(before.feeling))
    assert after.ignored_loss == pytest.approx(before.ignored_loss)


def test_decay_negative_minutes() -> None:
    with pytest.raises(ValueError):
        rules.decay(_state(), TEMPERAMENT, -1)


def test_appraise_praise() -> None:
    event = _event(EventKind.USER_MESSAGE, {"class": "praise"})

    assert rules.appraise(event) == PRAISE


def test_appraise_class_outside_set() -> None:
    event = _event(EventKind.USER_MESSAGE, {"class": "sarcasm"})

    assert rules.appraise(event) == ZERO


@pytest.mark.parametrize("kind", [EventKind.PAUSED, EventKind.RESUMED])
def test_appraise_pause_is_nothing(kind: EventKind) -> None:
    assert rules.appraise(_event(kind)) == ZERO


def test_appraise_passed_over_at_desk() -> None:
    event = _event(EventKind.MESSAGE_PASSED_OVER, {"at_desk": True})

    assert rules.appraise(event) == IGNORED


def test_appraise_passed_over_away() -> None:
    event = _event(EventKind.MESSAGE_PASSED_OVER, {"at_desk": False})

    assert rules.appraise(event) == ZERO


def test_appraise_commitment() -> None:
    finished = _event(EventKind.COMMITMENT_CLOSED, {"finished": True})
    dropped = _event(EventKind.COMMITMENT_CLOSED, {"finished": False})

    assert rules.appraise(finished) == Pad(0.30, 0.10, 0.05)
    assert rules.appraise(dropped) == ZERO


def test_apply_praise_from_rest() -> None:
    state = rules.apply(_state(), PRAISE, TEMPERAMENT)

    assert _axes(state.feeling) == pytest.approx((0.50, 0.20, 0.10))
    assert _axes(state.mood) == pytest.approx((0.30, 0.08, 0.04))


def test_apply_limits_each_axis() -> None:
    eager = replace(TEMPERAMENT, reactivity=1.0)

    state = rules.apply(_state(mood=Pad(0.90, 0.0, 0.0)), Pad(0.50, 0.0, 0.0), eager)

    assert state.mood.pleasure == 1.0


def test_sadden_lowers_mood_only() -> None:
    state = rules.sadden(_state(), IGNORED, TEMPERAMENT)

    assert state.mood.pleasure == pytest.approx(-0.02)
    assert state.feeling == ZERO
    assert state.ignored_loss == pytest.approx(0.12)
    assert not state.floor_reached


def test_sadden_stops_at_floor() -> None:
    before = _state(mood=Pad(-0.26, 0.0, 0.0), ignored_loss=0.36)

    state = rules.sadden(before, IGNORED, TEMPERAMENT)

    assert state.mood.pleasure == pytest.approx(-0.30)
    assert state.floor_reached
    assert state.ignored_loss == pytest.approx(0.40)


def test_sadden_below_floor() -> None:
    before = _state(mood=Pad(-0.50, 0.0, 0.0))

    state = rules.sadden(before, IGNORED, TEMPERAMENT)

    assert state.mood.pleasure == pytest.approx(-0.50)
    assert state.floor_reached
    assert state.ignored_loss == pytest.approx(0.0)


def test_restore_after_talk() -> None:
    before = _state(mood=Pad(-0.30, 0.0, 0.0), ignored_loss=0.40)

    state = rules.restore_after_talk(before)

    assert state.mood.pleasure == pytest.approx(-0.02)
    assert state.ignored_loss == 0.0


def test_restore_without_loss() -> None:
    before = _state(mood=Pad(-0.30, 0.0, 0.0))

    assert rules.restore_after_talk(before) == before


def test_feel_praise_illustration() -> None:
    state = rules.at_rest(TEMPERAMENT, MONDAY, 0)

    state = rules.feel(
        state, _event(EventKind.USER_MESSAGE, {"class": "praise"}), TEMPERAMENT
    )
    assert _axes(state.shown()) == pytest.approx((0.80, 0.28, 0.14))
    assert rules.name(state.shown()) == "lively"

    later = _event(EventKind.FOREGROUND_APP, at=MONDAY + timedelta(minutes=30), seq=2)
    state = rules.feel(state, later, TEMPERAMENT)
    assert _axes(state.feeling) == pytest.approx((0.25, 0.10, 0.05))
    assert rules.name(state.shown()) == "lively"

    evening = _event(EventKind.FOREGROUND_APP, at=MONDAY + timedelta(hours=12), seq=3)
    state = rules.feel(state, evening, TEMPERAMENT)
    assert _axes(state.mood) == pytest.approx((0.20, 0.04, 0.02))
    assert rules.name(state.shown()) == "calm"


def test_feel_ignored_illustration() -> None:
    state = rules.at_rest(TEMPERAMENT, MONDAY, 0)
    pleasures = []
    floors = []

    for seq in range(1, 5):
        ignored = _event(EventKind.MESSAGE_PASSED_OVER, {"at_desk": True}, seq=seq)
        state = rules.feel(state, ignored, TEMPERAMENT)
        pleasures.append(state.mood.pleasure)
        floors.append(state.floor_reached)

    assert pleasures == pytest.approx([-0.02, -0.14, -0.26, -0.30])
    assert floors == [False, False, False, True]

    talk = _event(EventKind.USER_MESSAGE, {"class": "nothing"}, seq=5)
    state = rules.feel(state, talk, TEMPERAMENT)
    assert state.mood.pleasure == pytest.approx(-0.02)
    assert not state.floor_reached


def test_feel_records_seq_and_time() -> None:
    at = MONDAY + timedelta(minutes=5)

    state = rules.feel(
        _state(), _event(EventKind.SESSION_OPENED, at=at, seq=7), TEMPERAMENT
    )

    assert state.computed_to_seq == 7
    assert state.computed_at == at


def test_feel_clock_went_back() -> None:
    before = _state(feeling=PRAISE)
    earlier = _event(EventKind.FOREGROUND_APP, at=MONDAY - timedelta(hours=1))

    state = rules.feel(before, earlier, TEMPERAMENT)

    assert _axes(state.feeling) == pytest.approx(_axes(PRAISE))


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        (Pad(0.10, 0.0, 0.0), "calm"),
        (Pad(0.20, 0.04, 0.0), "calm"),
        (Pad(0.54, 0.18, 0.0), "lively"),
        (Pad(0.50, -0.10, 0.0), "pleased"),
        (Pad(-0.30, 0.30, 0.0), "restless"),
        (Pad(-0.30, 0.0, 0.0), "low"),
    ],
)
def test_name(point: Pad, expected: str) -> None:
    assert rules.name(point) == expected


def test_expression_calm() -> None:
    face = rules.expression(Pad(0.10, 0.0, 0.0))

    assert (face.preset, face.weight) == ("neutral", 1.0)


def test_expression_lively() -> None:
    face = rules.expression(Pad(0.80, 0.28, 0.14))

    assert face.preset == "happy"
    assert face.weight == pytest.approx(0.8667, abs=1e-4)


def test_expression_weight_edges() -> None:
    weakest = rules.expression(Pad(0.25, 0.10, 0.0))
    strongest = rules.expression(Pad(1.0, 0.50, 0.0))

    assert (weakest.preset, weakest.weight) == ("happy", pytest.approx(0.5))
    assert (strongest.preset, strongest.weight) == ("happy", pytest.approx(1.0))


def test_expression_moods_off() -> None:
    face = rules.expression(Pad(0.80, 0.28, 0.14), moods_on=False)

    assert (face.preset, face.weight) == ("neutral", 1.0)
