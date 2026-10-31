from src.domain.ports import ReplyFailed


def test_reply_failed_keeps_sentence() -> None:
    assert str(ReplyFailed("fix it")) == "fix it"
