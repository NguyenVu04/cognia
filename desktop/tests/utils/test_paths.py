import pytest

from src.utils.paths import resource


def test_resource_missing_raises() -> None:
    with pytest.raises(FileNotFoundError):
        resource("no-such-file")
