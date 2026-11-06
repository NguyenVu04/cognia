import pytest

from src.domain.conversation.models import Interpretation


def test_interpretation_keeps_fields() -> None:
    found = Interpretation(8, ("Is writing a thesis",))

    assert found.importance == 8
    assert found.facts == ("Is writing a thesis",)


@pytest.mark.parametrize("importance", [0, 11])
def test_interpretation_refuses_importance_outside_range(importance: int) -> None:
    with pytest.raises(ValueError):
        Interpretation(importance, ())


def test_interpretation_defaults() -> None:
    found = Interpretation(3, ())

    assert (found.event_class, found.confidence, found.crisis) == (None, 0.0, False)


@pytest.mark.parametrize("confidence", [0.0, 1.0])
def test_confidence_bounds_kept(confidence: float) -> None:
    assert Interpretation(3, (), confidence=confidence).confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_confidence_outside_range(confidence: float) -> None:
    with pytest.raises(ValueError):
        Interpretation(3, (), confidence=confidence)


def test_summary_keeps_fields() -> None:
    from src.domain.conversation.models import Summary

    assert Summary("They talked.", 4) == Summary("They talked.", 4)


@pytest.mark.parametrize(("text", "covers"), [("  ", 3), ("They talked.", 0)])
def test_summary_refuses(text: str, covers: int) -> None:
    from src.domain.conversation.models import Summary

    with pytest.raises(ValueError):
        Summary(text, covers)
