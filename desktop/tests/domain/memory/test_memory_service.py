from datetime import datetime, timezone

import pytest

from src.domain.memory.memory_service import MemoryService
from src.domain.memory.models import TOLD, MemoryItem

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self) -> None:
        self.added: list = []
        self.calls: list[tuple] = []
        self.model: str | None = None

    def items(self) -> list[MemoryItem]:
        return list(self.added)

    def add(self, entry) -> None:
        self.added.append(entry)

    def correct(self, entry, text: str) -> None:
        self.calls.append(("correct", entry.id, text))

    def remove(self, entry) -> None:
        self.calls.append(("remove", entry.id))

    def set_embedding(self, entry, vector) -> None:
        self.calls.append(("set_embedding", entry.id, vector))

    def link(self, message_id, entries, now) -> None:
        self.calls.append(("link", message_id, [e.id for e in entries], now))

    def embedding_model(self) -> str | None:
        return self.model

    def reset_embeddings(self, model: str) -> None:
        self.calls.append(("reset", model))
        self.model = model

    def close(self) -> None:
        pass


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def service(store: FakeStore) -> MemoryService:
    return MemoryService(store)


def chosen() -> tuple[str, ...]:
    return ("Is writing a thesis", "Has a cat")


def test_remember_stores_each_fact_as_told(service, store) -> None:
    vectors = {"Is writing a thesis": (1.0, 0.0)}

    stored = service.remember(chosen(), 6, "m1", vectors, NOW)

    first, second = store.added
    assert stored == (first, second)
    assert [e.text for e in stored] == ["Is writing a thesis", "Has a cat"]
    assert {(e.kind, e.importance, e.source_message_id) for e in stored} == {
        (TOLD, 6, "m1")
    }
    assert first.recorded_at == NOW
    assert first.embedding == (1.0, 0.0)
    assert second.embedding is None
    assert first.id != second.id


def test_remember_nothing(service, store) -> None:
    assert service.remember((), 7, "m1", {}, NOW) == ()
    assert store.added == []


def test_entries_returns_items(service, store) -> None:
    stored = service.remember(chosen()[:1], 7, "m1", {}, NOW)

    assert service.entries() == list(stored)


def test_correct_tidies(service, store) -> None:
    entry, _ = service.remember(chosen(), 7, "m1", {}, NOW)

    service.correct(entry, "  Works   on a thesis ")

    assert store.calls == [("correct", entry.id, "Works on a thesis")]


def test_correct_refuses_blank(service, store) -> None:
    entry, _ = service.remember(chosen(), 7, "m1", {}, NOW)

    with pytest.raises(ValueError):
        service.correct(entry, "   ")
    assert store.calls == []


def test_use_links(service, store) -> None:
    entries = service.remember(chosen(), 7, "m1", {}, NOW)

    service.use("m2", entries, NOW)

    assert store.calls == [("link", "m2", [e.id for e in entries], NOW)]


def test_use_nothing(service, store) -> None:
    service.use("m2", [], NOW)

    assert store.calls == []


def test_missing_vectors(service, store) -> None:
    service.remember(chosen(), 7, "m1", {"Is writing a thesis": (1.0,)}, NOW)

    assert [e.text for e in service.missing_vectors()] == ["Has a cat"]


def test_check_model_same(service, store) -> None:
    store.model = "embedding.gguf:36685152"

    assert service.check_model("embedding.gguf:36685152") is False
    assert store.calls == []


def test_check_model_different(service, store) -> None:
    store.model = "embedding.gguf:1"

    assert service.check_model("embedding.gguf:36685152") is True
    assert store.calls == [("reset", "embedding.gguf:36685152")]


def test_check_model_unrecorded(service, store) -> None:
    assert service.check_model("embedding.gguf:36685152") is True
