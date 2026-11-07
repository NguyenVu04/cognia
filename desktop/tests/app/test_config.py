from pathlib import Path

import pytest

from src.app import config

DESKTOP = Path(config.__file__).resolve().parents[2]


def test_shipped_defaults_load() -> None:
    assert config.HISTORY_MAX_CHARS > 0
    assert config.CHAT_CONTEXT > 0
    assert config.CHAT_CACHE_RAM_MIB >= 0
    assert config.INTERPRET_MAX_TOKENS > 0
    assert config.SUMMARY_MAX_TOKENS > 0
    assert 0 <= config.EMBEDDING_BASELINE < 1
    assert 0 < config.NEAR_DUPLICATE <= 1


def test_model_paths_resolve_under_desktop_models() -> None:
    for value in (
        config.LLAMA_SERVER_VULKAN,
        config.LLAMA_SERVER_CPU,
        config.CHAT_MODEL,
        config.EMBEDDING_MODEL,
    ):
        assert config.model_path(value).is_relative_to(DESKTOP / "models")


def test_model_path_keeps_absolute(tmp_path: Path) -> None:
    assert config.model_path(str(tmp_path / "chat.gguf")) == tmp_path / "chat.gguf"


def test_database_path_in_folder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path))

    assert config.database_path() == tmp_path / config.DATABASE_NAME


def test_database_path_relative(monkeypatch) -> None:
    monkeypatch.setattr(config, "DATABASE_PATH", "data/cognia.sqlite3")

    assert config.database_path() == DESKTOP / "data" / "cognia.sqlite3"


@pytest.mark.parametrize("key", ["OLLAMA_MODEL", "OLLAMA_BASE_URL"])
def test_ollama_keys_are_gone(key: str) -> None:
    assert not hasattr(config, key)
