from src.domain.ports import EmbedFailed, InterpretFailed, MemoryStoreFailed


def test_interpret_failed_keeps_sentence() -> None:
    assert str(InterpretFailed("fix it")) == "fix it"


def test_embed_failed_keeps_sentence() -> None:
    assert str(EmbedFailed("fix it")) == "fix it"


def test_memory_store_failed_keeps_sentence() -> None:
    assert str(MemoryStoreFailed("fix it")) == "fix it"
