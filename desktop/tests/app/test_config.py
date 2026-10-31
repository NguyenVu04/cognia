from src.app import config


def test_shipped_defaults_load() -> None:
    assert config.HISTORY_MESSAGES > 0
