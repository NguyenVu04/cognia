from datetime import date

import pytest

from src.domain.conversation.models import Interpretation, SaidCommitment


def test_interpretation_keeps_fields() -> None:
    said = SaidCommitment("Send chapter 3", date(2026, 11, 6))
    found = Interpretation(8, ("Is writing a thesis",), (said,))

    assert found.importance == 8
    assert found.commitments[0].due_on == date(2026, 11, 6)


@pytest.mark.parametrize("importance", [0, 11])
def test_interpretation_refuses_importance_outside_range(importance: int) -> None:
    with pytest.raises(ValueError):
        Interpretation(importance, (), ())


def test_said_commitment_refuses_blank_text() -> None:
    with pytest.raises(ValueError):
        SaidCommitment("   ", None)
