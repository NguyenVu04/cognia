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
