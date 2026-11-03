import pytest

from src.domain.emotion.models import Pad, Temperament

REST = Pad(0.10, -0.05, 0.00)


def test_valid_temperament() -> None:
    temperament = Temperament(0.4, 30.0, 720.0, REST)

    assert temperament.rest == REST


@pytest.mark.parametrize("reactivity", [0.0, 1.0])
def test_reactivity_bounds_accepted(reactivity: float) -> None:
    assert Temperament(reactivity, 30.0, 720.0, REST).reactivity == reactivity


def test_reactivity_below_zero() -> None:
    with pytest.raises(ValueError):
        Temperament(-0.1, 30.0, 720.0, REST)


def test_reactivity_above_one() -> None:
    with pytest.raises(ValueError):
        Temperament(1.1, 30.0, 720.0, REST)


def test_feeling_half_life_zero() -> None:
    with pytest.raises(ValueError):
        Temperament(0.4, 0.0, 720.0, REST)


def test_mood_half_life_negative() -> None:
    with pytest.raises(ValueError):
        Temperament(0.4, 30.0, -1.0, REST)


def test_rest_axis_out_of_range() -> None:
    with pytest.raises(ValueError):
        Temperament(0.4, 30.0, 720.0, Pad(1.01, 0.0, 0.0))


def test_rest_axis_at_limit() -> None:
    rest = Pad(-1.0, 1.0, -1.0)

    assert Temperament(0.4, 30.0, 720.0, rest).rest == rest
