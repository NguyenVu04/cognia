from src.domain.ports import EventLogFailed


def test_event_log_failed_keeps_sentence() -> None:
    assert str(EventLogFailed("fix it")) == "fix it"
