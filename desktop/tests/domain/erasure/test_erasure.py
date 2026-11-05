import pytest

from src.domain.erasure import rules
from src.domain.erasure.erasure_service import ErasureService
from src.domain.erasure.models import ErasureReport, Group, GroupCount, Level
from src.domain.ports import ErasureFailed

MEMORY_GROUPS = (
    Group.CONVERSATIONS,
    Group.MEMORY,
    Group.SESSIONS,
    Group.LEARNING,
    Group.JOURNAL,
    Group.SPEECH,
    Group.EVENTS,
)


class FakeStore:
    def __init__(self) -> None:
        self.failing: set[Group] = set()
        self.compact_fails = False
        self.erased: list[Group] = []
        self.compacted = 0

    def count(self, group: Group) -> int:
        return len(group.value)

    def erase(self, group: Group) -> None:
        if group in self.failing:
            raise ErasureFailed("no")
        self.erased.append(group)

    def compact(self) -> None:
        if self.compact_fails:
            raise ErasureFailed("no")
        self.compacted += 1


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


def test_groups_memory() -> None:
    assert rules.groups(Level.MEMORY) == MEMORY_GROUPS


def test_groups_everything() -> None:
    assert rules.groups(Level.EVERYTHING) == (
        *MEMORY_GROUPS,
        Group.CHARACTER,
        Group.SETTINGS,
    )


def test_preview_counts_in_order(store) -> None:
    counts = ErasureService(store).preview(Level.MEMORY)

    assert counts[0] == GroupCount(Group.CONVERSATIONS, len("conversations"))
    assert [c.group for c in counts] == list(MEMORY_GROUPS)


def test_erase_all_succeed(store) -> None:
    report = ErasureService(store).erase(Level.EVERYTHING)

    assert report.complete
    assert report.erased == rules.groups(Level.EVERYTHING)
    assert store.compacted == 1


def test_erase_continues_after_a_failure(store) -> None:
    store.failing = {Group.SESSIONS}

    report = ErasureService(store).erase(Level.MEMORY)

    assert report.failed == (Group.SESSIONS,)
    assert Group.EVENTS in report.erased
    assert Group.SESSIONS not in report.erased
    assert store.compacted == 1
    assert not report.complete


def test_compact_failure_is_reported(store) -> None:
    store.compact_fails = True

    report = ErasureService(store).erase(Level.MEMORY)

    assert report.compacted is False
    assert not report.complete


def test_second_erase_removes_what_is_left(store) -> None:
    store.failing = {Group.SESSIONS}
    service = ErasureService(store)
    service.erase(Level.MEMORY)
    store.failing = set()

    assert service.erase(Level.MEMORY).complete


def test_report_complete_needs_compaction() -> None:
    assert not ErasureReport((Group.MEMORY,), (), compacted=False).complete
