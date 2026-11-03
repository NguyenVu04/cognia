from datetime import datetime, timezone

import pytest

from src.domain.emotion.models import EmotionState, Expression, Pad

MONDAY = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)


def _axes(point: Pad) -> tuple[float, float, float]:
    return (point.pleasure, point.arousal, point.dominance)


def test_shown_adds_feeling_to_mood() -> None:
    state = EmotionState(Pad(0.30, 0.08, 0.04), Pad(0.50, 0.20, 0.10), 1, MONDAY)

    assert _axes(state.shown()) == pytest.approx((0.80, 0.28, 0.14))


def test_shown_is_limited() -> None:
    state = EmotionState(Pad(0.90, 0.0, 0.0), Pad(0.50, 0.0, 0.0), 1, MONDAY)

    assert _axes(state.shown()) == pytest.approx((1.0, 0.0, 0.0))


@pytest.mark.parametrize("weight", [0.0, 1.0])
def test_expression_weight_bounds_accepted(weight: float) -> None:
    assert Expression("happy", weight).weight == weight


@pytest.mark.parametrize("weight", [1.2, -0.1])
def test_expression_weight_out_of_range(weight: float) -> None:
    with pytest.raises(ValueError):
        Expression("happy", weight)
