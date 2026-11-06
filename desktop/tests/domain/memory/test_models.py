from datetime import datetime, timezone

import pytest

from src.domain.memory.models import NOTICED, TOLD, Calibration, MemoryItem

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)


def item(**fields) -> MemoryItem:
    values = dict(
        id="i1", kind=TOLD, text="Is writing a thesis", reason=None,
        source_message_id=None, importance=7, last_retrieved_at=None,
        recorded_at=NOW, embedding=None,
    )
    values.update(fields)
    return MemoryItem(**values)


def test_told_item_needs_no_reason() -> None:
    assert item().reason is None


def test_item_refuses_unknown_kind() -> None:
    with pytest.raises(ValueError):
        item(kind="maybe")


def test_item_refuses_blank_text() -> None:
    with pytest.raises(ValueError):
        item(text="  ")


def test_item_refuses_importance_0() -> None:
    with pytest.raises(ValueError):
        item(importance=0)


def test_noticed_item_needs_reason() -> None:
    with pytest.raises(ValueError):
        item(kind=NOTICED, reason=" ")


def test_noticed_item_with_reason() -> None:
    assert item(kind=NOTICED, reason="18 of 21 sessions").kind == NOTICED


def test_item_refuses_importance_11() -> None:
    with pytest.raises(ValueError):
        item(importance=11)


def test_item_without_importance() -> None:
    assert item(importance=None).importance is None


@pytest.mark.parametrize("baseline", [-0.1, 1.0])
def test_calibration_refuses_baseline(baseline: float) -> None:
    with pytest.raises(ValueError):
        Calibration(baseline, 0.95)


@pytest.mark.parametrize("near", [0.0, 1.1])
def test_calibration_refuses_near_duplicate(near: float) -> None:
    with pytest.raises(ValueError):
        Calibration(0.45, near)
