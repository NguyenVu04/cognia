from datetime import datetime

from src.domain.conversation.models import USER, Message


def test_new_message_from_user() -> None:
    message = Message.new("c1", USER, "hi", datetime(2026, 10, 31, 12, 0))

    assert message.from_user
    assert message.note == ""
