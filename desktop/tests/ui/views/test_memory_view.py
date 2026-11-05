from datetime import date, datetime, timezone

import pytest
from PySide6.QtWidgets import QLabel

from src.domain.memory.models import TOLD, Commitment, MemoryItem
from src.ui.views.memory import MemoryItemCard, MemoryView

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)


def item(id: str, text: str) -> MemoryItem:
    return MemoryItem(
        id=id, kind=TOLD, text=text, reason=None, source_message_id=None,
        importance=5, last_retrieved_at=None, recorded_at=NOW, embedding=None,
    )


COMMITMENT = Commitment(
    id="c1", text="Send chapter 3", due_on=date(2026, 11, 6), source_message_id=None,
    importance=8, last_retrieved_at=None, recorded_at=NOW, embedding=None,
)


@pytest.fixture
def view(qtbot) -> MemoryView:
    shown = MemoryView()
    qtbot.addWidget(shown)
    shown.setEntries([item("i1", "Is writing a thesis"), item("i2", "Has a cat")],
                     [COMMITMENT])
    return shown


def cards(layout) -> list[MemoryItemCard]:
    return [layout.itemAt(i).widget() for i in range(layout.count())]


def collect(signal) -> list:
    caught: list = []
    signal.connect(lambda *args: caught.append(args))
    return caught


def test_told_column_holds_items_and_commitments(view: MemoryView) -> None:
    told = cards(view._told)

    assert len(told) == 3
    assert cards(view._noticed) == []
    assert "(3 items)" in view.strip_text.text()


def test_commitment_shows_due_day(view: MemoryView) -> None:
    texts = [w.text() for w in cards(view._told)[2].findChildren(QLabel)]

    assert "5 Nov · due 6 Nov" in texts


def test_delete_emits_entry(view: MemoryView) -> None:
    caught = collect(view.removeRequested)

    cards(view._told)[2].remove_button.click()

    assert caught == [(COMMITMENT,)]


def test_edit_emits_correction(view: MemoryView) -> None:
    caught = collect(view.correctRequested)
    card = cards(view._told)[0]

    card.edit_button.click()
    card.edit.setText("Works on a thesis")
    card.edit_button.click()

    assert caught[0][0].id == "i1"
    assert caught[0][1] == "Works on a thesis"


def test_blank_edit_reverts(view: MemoryView) -> None:
    caught = collect(view.correctRequested)
    card = cards(view._told)[0]

    card.edit_button.click()
    card.edit.setText("   ")
    card.edit_button.click()

    assert caught == []
    assert card.edit.text() == "Is writing a thesis"


def test_show_error_hides_the_list(view: MemoryView) -> None:
    view.showError("The remembered items cannot be read.")

    assert view.columns.isHidden()
    assert not view.error.isHidden()
    assert "cannot be read" in view.error.text()


def test_erase_buttons(view: MemoryView) -> None:
    caught = collect(view.eraseRequested)

    view.erase_memory.click()
    view.erase_everything.click()

    assert caught == [("memory",), ("everything",)]


def test_character_name_in_strip(view: MemoryView) -> None:
    view.setCharacterName("Rin")

    assert "keep Rin" in view.strip_text.text()
