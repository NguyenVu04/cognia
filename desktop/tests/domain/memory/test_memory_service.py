from datetime import date, datetime, timezone

import pytest

from src.domain.conversation.models import SaidCommitment
from src.domain.memory.memory_service import MemoryService
from src.domain.memory.models import TOLD, Commitment, MemoryItem, Selection

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self) -> None:
        self.added: list = []
        self.calls: list[tuple] = []
        self.model: str | None = None

    def items(self) -> list[MemoryItem]:
        return [e for e in self.added if isinstance(e, MemoryItem)]

    def commitments(self) -> list[Commitment]:
        return [e for e in self.added if isinstance(e, Commitment)]

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


def chosen() -> Selection:
    return Selection(
        ("Is writing a thesis",),
        (SaidCommitment("Send chapter 3", date(2026, 11, 6)),),
    )


def test_remember_stores_told_item_and_commitment(service, store) -> None:
    vectors = {"Is writing a thesis": (1.0, 0.0)}

    stored = service.remember(chosen(), 7, "m1", vectors, NOW)

    item, commitment = store.added
    assert stored == (item, commitment)
    assert (item.kind, item.text, item.importance) == (TOLD, "Is writing a thesis", 7)
    assert (item.source_message_id, item.recorded_at) == ("m1", NOW)
    assert item.embedding == (1.0, 0.0)
    assert (commitment.text, commitment.due_on) == ("Send chapter 3", date(2026, 11, 6))
    assert commitment.embedding is None
    assert item.id != commitment.id


def test_remember_empty_selection(service, store) -> None:
    assert service.remember(Selection((), ()), 7, "m1", {}, NOW) == ()
    assert store.added == []


def test_entries_holds_both_kinds(service, store) -> None:
    service.remember(chosen(), 7, "m1", {}, NOW)

    assert len(service.entries()) == 2


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

    assert [e.text for e in service.missing_vectors()] == ["Send chapter 3"]


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
