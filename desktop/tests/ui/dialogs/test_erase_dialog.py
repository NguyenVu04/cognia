import pytest
from PySide6.QtWidgets import QLabel

from src.domain.erasure.models import ErasureReport, Group, GroupCount, Level
from src.ui.dialogs.erase_dialog import EraseDialog

COUNTS = [
    GroupCount(Group.CONVERSATIONS, 12),
    GroupCount(Group.MEMORY, 3),
    GroupCount(Group.SESSIONS, 0),
]


def texts(dialog: EraseDialog) -> list[str]:
    return [label.text() for label in dialog.findChildren(QLabel)]


@pytest.fixture
def dialog(qtbot) -> EraseDialog:
    shown = EraseDialog(Level.MEMORY, COUNTS, "Rin")
    qtbot.addWidget(shown)
    return shown


def test_lists_groups_with_rows(dialog: EraseDialog) -> None:
    shown = " ".join(texts(dialog))

    assert "Messages in conversations" in shown
    assert "Things you told me, and commitments" in shown
    assert "Work sessions" not in shown
    assert "This cannot be undone." in shown


def test_erase_button_counts(dialog: EraseDialog) -> None:
    assert dialog.erase.text() == "Erase 15 items"


def test_confirm(dialog: EraseDialog, qtbot) -> None:
    with qtbot.waitSignal(dialog.confirmed):
        dialog.erase.click()


def test_partial_report_offers_retry(dialog: EraseDialog, qtbot) -> None:
    dialog.showReport(
        ErasureReport((Group.CONVERSATIONS,), (Group.MEMORY,), compacted=True)
    )
    shown = " ".join(texts(dialog))

    assert "Removed: messages in conversations." in shown
    assert "Not removed: things you told me, and commitments." in shown
    with qtbot.waitSignal(dialog.retryRequested):
        dialog.retry.click()


def test_complete_report(dialog: EraseDialog) -> None:
    dialog.showReport(ErasureReport((Group.CONVERSATIONS,), (), compacted=True))

    assert "Nothing of it remains on the disk." in " ".join(texts(dialog))


def test_not_working_at_first(dialog: EraseDialog) -> None:
    assert dialog.working is False


def test_working_after_show_working(dialog: EraseDialog) -> None:
    dialog.showWorking()

    assert dialog.working is True
    assert "Erasing…" in texts(dialog)


def test_report_ends_working(dialog: EraseDialog) -> None:
    dialog.showWorking()
    dialog.showReport(ErasureReport((Group.CONVERSATIONS,), (), compacted=True))

    assert dialog.working is False


def test_stopped_offers_retry(dialog: EraseDialog, qtbot) -> None:
    dialog.showWorking()
    dialog.showStopped()

    assert dialog.working is False
    assert "Erasing stopped partway, so some of it may still be on the disk." in (
        " ".join(texts(dialog))
    )
    with qtbot.waitSignal(dialog.retryRequested):
        dialog.retry.click()


def test_nothing_to_erase(qtbot) -> None:
    empty = EraseDialog(Level.MEMORY, [GroupCount(Group.MEMORY, 0)], "Rin")
    qtbot.addWidget(empty)

    assert not hasattr(empty, "erase")
    assert "There is nothing to erase." in " ".join(texts(empty))
