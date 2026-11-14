import pytest

from src.domain.erasure import rules
from src.domain.erasure.erasure_service import ErasureService
from src.domain.erasure.models import ErasureReport, Group, GroupCount, Level
from src.domain.ports import ErasureFailed

MEMORY_GROUPS = (
    Group.CONVERSATIONS,
    Group.MEMORY,
    Group.DESK,
    Group.LEARNING,
    Group.SPEECH,
    Group.EVENTS,
    Group.DIAGNOSTICS,
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


class FakeLog:
    def __init__(self, lines: int = 7) -> None:
        self.lines = lines
        self.failing = False

    def entries(self) -> int:
        return self.lines

    def erase(self) -> None:
        if self.failing:
            raise ErasureFailed("no")
        self.lines = 0


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def log() -> FakeLog:
    return FakeLog()


def test_groups_memory() -> None:
    assert rules.groups(Level.MEMORY) == MEMORY_GROUPS


def test_groups_everything() -> None:
    assert rules.groups(Level.EVERYTHING) == (
        *MEMORY_GROUPS,
        Group.CHARACTER,
        Group.SETTINGS,
    )


def test_preview_counts_in_order(store, log) -> None:
    counts = ErasureService(store, log).preview(Level.MEMORY)

    assert counts[0] == GroupCount(Group.CONVERSATIONS, len("conversations"))
    assert [c.group for c in counts] == list(MEMORY_GROUPS)


def test_erase_all_succeed(store, log) -> None:
    report = ErasureService(store, log).erase(Level.EVERYTHING)

    assert report.complete
    assert report.erased == rules.groups(Level.EVERYTHING)
    assert store.compacted == 1


def test_erase_continues_after_a_failure(store, log) -> None:
    store.failing = {Group.DESK}

    report = ErasureService(store, log).erase(Level.MEMORY)

    assert report.failed == (Group.DESK,)
    assert Group.EVENTS in report.erased
    assert Group.DESK not in report.erased
    assert store.compacted == 1
    assert not report.complete


def test_compact_failure_is_reported(store, log) -> None:
    store.compact_fails = True

    report = ErasureService(store, log).erase(Level.MEMORY)

    assert report.compacted is False
    assert not report.complete


def test_second_erase_removes_what_is_left(store, log) -> None:
    store.failing = {Group.DESK}
    service = ErasureService(store, log)
    service.erase(Level.MEMORY)
    store.failing = set()

    assert service.erase(Level.MEMORY).complete


def test_report_complete_needs_compaction() -> None:
    assert not ErasureReport((Group.MEMORY,), (), compacted=False).complete


def test_both_levels_include_diagnostics() -> None:
    assert Group.DIAGNOSTICS in rules.groups(Level.MEMORY)
    assert Group.DIAGNOSTICS in rules.groups(Level.EVERYTHING)


def test_preview_counts_log_lines(store, log) -> None:
    counts = ErasureService(store, log).preview(Level.MEMORY)

    assert counts[-1] == GroupCount(Group.DIAGNOSTICS, 7)


def test_erase_removes_log_and_not_through_the_store(store, log) -> None:
    report = ErasureService(store, log).erase(Level.MEMORY)

    assert log.lines == 0
    assert Group.DIAGNOSTICS in report.erased
    assert Group.DIAGNOSTICS not in store.erased


def test_failed_log_erasure_is_reported(store, log) -> None:
    log.failing = True

    report = ErasureService(store, log).erase(Level.MEMORY)

    assert report.failed == (Group.DIAGNOSTICS,)
    assert Group.EVENTS in report.erased
    assert not report.complete
