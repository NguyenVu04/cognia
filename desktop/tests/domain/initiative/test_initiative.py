from importlib import import_module


def test_package_imports() -> None:
    assert import_module("src.domain.initiative")
