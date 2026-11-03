from datetime import datetime, timezone

import pytest

from src.domain.events.models import Event, EventKind, MessageClass

MONDAY = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)


def _event(seq: int = 1, importance: int | None = 5) -> Event:
    return Event(
        seq, MONDAY, 60, EventKind.USER_MESSAGE, {"class": "praise"}, importance
    )


def test_event_keeps_fields() -> None:
    event = _event()

    assert event.seq == 1
    assert event.occurred_at == MONDAY
    assert event.utc_offset_min == 60
    assert event.kind is EventKind.USER_MESSAGE
    assert event.payload == {"class": "praise"}
    assert event.importance == 5


@pytest.mark.parametrize("importance", [1, 10, None])
def test_importance_bounds_accepted(importance: int | None) -> None:
    assert _event(importance=importance).importance == importance


@pytest.mark.parametrize("importance", [0, 11])
def test_importance_out_of_range(importance: int) -> None:
    with pytest.raises(ValueError):
        _event(importance=importance)


def test_seq_below_one() -> None:
    with pytest.raises(ValueError):
        _event(seq=0)


def test_kind_outside_closed_set() -> None:
    with pytest.raises(ValueError):
        EventKind("sarcasm")


def test_message_class_outside_set() -> None:
    with pytest.raises(ValueError):
        MessageClass("sarcasm")
