from datetime import datetime, timedelta, timezone

import pytest

from src.domain.companion import rules
from src.domain.companion.models import CompanionState, ShowExpression, StepResult
from src.domain.emotion import rules as emotion_rules
from src.domain.emotion.models import Expression, Pad, Temperament
from src.domain.events.models import Event, EventKind, Payload

MONDAY = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
REST = Pad(0.10, 0.0, 0.0)
ZERO = Pad(0.0, 0.0, 0.0)
V1 = Temperament(0.4, 30.0, 720.0, REST)
V2 = Temperament(0.4, 60.0, 720.0, Pad(-0.10, 0.0, 0.0))
TEMPERAMENTS = {"v1": V1, "v2": V2}
NEUTRAL = ShowExpression(Expression("neutral", 1.0))


def _axes(point: Pad) -> tuple[float, float, float]:
    return (point.pleasure, point.arousal, point.dominance)


def _event(
    seq: int, minutes: int, kind: EventKind, payload: Payload | None = None
) -> Event:
    return Event(seq, MONDAY + timedelta(minutes=minutes), 0, kind, payload or {}, None)


def _chosen(version_id: str = "v1", seq: int = 1, minutes: int = 0) -> Event:
    return _event(seq, minutes, EventKind.CHARACTER_CHANGED, {"version_id": version_id})


def _praise(seq: int, minutes: int) -> Event:
    return _event(seq, minutes, EventKind.USER_MESSAGE, {"class": "praise"})


def _presence(seq: int, minutes: int) -> Event:
    return _event(seq, minutes, EventKind.PRESENCE)


def _moods(on: bool, seq: int, minutes: int) -> Event:
    payload = {"name": "moods_on", "value": on}
    return _event(seq, minutes, EventKind.SETTING_CHANGED, payload)


def _last(*events: Event) -> StepResult:
    state = rules.initial_state()
    for event in events:
        result = rules.step(state, event, TEMPERAMENTS)
        state = result.state
    return result


def test_initial_state() -> None:
    assert rules.initial_state() == CompanionState(None, True, None)


def test_step_before_character() -> None:
    state = rules.initial_state()

    result = rules.step(state, _presence(1, 0), TEMPERAMENTS)

    assert result == StepResult(state, (), None)


def test_step_first_character_rests() -> None:
    result = _last(_chosen())

    assert result.state == CompanionState(
        "v1", True, emotion_rules.at_rest(V1, MONDAY, 1)
    )
    assert result.effects == (NEUTRAL,)
    assert result.next_wake is None


def test_step_praise() -> None:
    result = _last(_chosen(), _praise(2, 10))

    assert _axes(result.state.emotion.mood) == pytest.approx((0.30, 0.08, 0.04))
    (effect,) = result.effects
    assert effect.expression.preset == "happy"
    assert effect.expression.weight == pytest.approx(0.867, abs=1e-3)


def test_step_decay_changes_face() -> None:
    result = _last(_chosen(), _praise(2, 10), _presence(3, 40))

    shown = result.state.emotion.shown()
    assert _axes(shown) == pytest.approx((0.544, 0.178, 0.089), abs=1e-3)
    (effect,) = result.effects
    assert effect.expression.preset == "happy"
    assert effect.expression.weight == pytest.approx(0.696, abs=1e-3)


def test_step_same_face_no_effect() -> None:
    assert _last(_chosen(), _presence(2, 10)).effects == ()


def test_step_moods_off_rests() -> None:
    result = _last(_chosen(), _praise(2, 10), _moods(False, 3, 20))

    assert result.state.moods_on is False
    assert result.state.emotion.mood == REST
    assert result.state.emotion.feeling == ZERO
    assert result.effects == (NEUTRAL,)


def test_step_moods_off_ignores_praise() -> None:
    result = _last(_chosen(), _moods(False, 2, 0), _praise(3, 10))

    assert result.state.emotion.mood == REST
    assert result.effects == ()


def test_step_moods_on_starts_from_rest() -> None:
    result = _last(
        _chosen(),
        _praise(2, 10),
        _moods(False, 3, 20),
        _moods(True, 4, 30),
        _praise(5, 40),
    )

    assert _axes(result.state.emotion.mood) == pytest.approx((0.30, 0.08, 0.04))


def test_step_other_setting_ignored() -> None:
    payload = {"name": "daily_ceiling", "value": 3}
    other = _event(2, 0, EventKind.SETTING_CHANGED, payload)

    assert _last(_chosen(), other).state.moods_on is True


def test_step_change_decays_under_old() -> None:
    result = _last(_chosen(), _praise(2, 10), _chosen("v2", 3, 40))

    assert result.state.version_id == "v2"
    # Under the half-life of v2 the feeling would be 0.354.
    assert _axes(result.state.emotion.feeling) == pytest.approx((0.25, 0.10, 0.05))


def test_step_change_moves_to_new_rest() -> None:
    result = _last(
        _chosen(), _praise(2, 10), _chosen("v2", 3, 10), _presence(4, 10 + 720)
    )

    assert _axes(result.state.emotion.mood) == pytest.approx((0.10, 0.04, 0.02))


def test_step_unknown_version() -> None:
    with pytest.raises(ValueError):
        rules.step(rules.initial_state(), _chosen("v9"), TEMPERAMENTS)


def test_step_missing_version_id() -> None:
    event = _event(1, 0, EventKind.CHARACTER_CHANGED)

    with pytest.raises(ValueError):
        rules.step(rules.initial_state(), event, TEMPERAMENTS)


def test_fold_empty() -> None:
    state = rules.initial_state()

    assert rules.fold(state, [], TEMPERAMENTS) == state


def test_fold_matches_steps() -> None:
    events = [_chosen(), _praise(2, 10), _presence(3, 40)]

    folded = rules.fold(rules.initial_state(), events, TEMPERAMENTS)

    assert folded == _last(*events).state


def test_fold_twice_equal() -> None:
    events = [_chosen(), _praise(2, 10), _moods(False, 3, 20), _chosen("v2", 4, 30)]

    first = rules.fold(rules.initial_state(), events, TEMPERAMENTS)
    second = rules.fold(rules.initial_state(), events, TEMPERAMENTS)

    assert first == second
