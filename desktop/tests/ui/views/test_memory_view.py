from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QLabel

from src.domain.learning.models import FREQUENCY, Adjustment, Learned, Pattern
from src.domain.memory.models import NOTICED, TOLD, MemoryItem
from src.ui.views.memory import (
    ALL,
    NOTICED_GROUP,
    LearnedCard,
    MemoryItemCard,
    MemoryView,
)

NOW = datetime.now(timezone.utc)


def item(id: str, text: str, *, kind: str = TOLD, days: int = 0) -> MemoryItem:
    return MemoryItem(
        id=id,
        kind=kind,
        text=text,
        reason="Said it twice" if kind == NOTICED else None,
        source_message_id=None,
        importance=5,
        last_retrieved_at=None,
        recorded_at=NOW - timedelta(days=days),
        embedding=None,
    )


@pytest.fixture
def view(qtbot) -> MemoryView:
    shown = MemoryView()
    qtbot.addWidget(shown)
    shown.setEntries(
        [
            item("i1", "Is writing a thesis"),
            item("i2", "Has a cat", days=20),
            item("i3", "Likes tea in the evening", kind=NOTICED),
        ]
    )
    return shown


def shown(view: MemoryView, kind) -> list:
    layout = view.sections
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    return [w for w in widgets if isinstance(w, kind)]


def collect(signal) -> list:
    caught: list = []
    signal.connect(lambda *args: caught.append(args))
    return caught


def test_three_groups(view: MemoryView) -> None:
    labels = [w.text() for w in view.findChildren(QLabel)]

    assert "YOU TOLD ME" in labels
    assert "I NOTICED" in labels
    assert "ABOUT ME" in labels
    assert len(shown(view, MemoryItemCard)) == 3


def test_noticed_card_shows_its_evidence(view: MemoryView) -> None:
    noticed = shown(view, MemoryItemCard)[2]
    texts = " ".join(w.text() for w in noticed.findChildren(QLabel))

    assert "Said it twice" in texts


def test_search_filters_and_shows_indicator(view: MemoryView) -> None:
    view.search.setText("cat")

    assert [c._text for c in shown(view, MemoryItemCard)] == ["Has a cat"]
    assert not view.filter_bar.isHidden()
    assert "1 item shown" in view.filter_text.text()


def test_period_filter(view: MemoryView) -> None:
    view._period_buttons[7].click()

    assert "Has a cat" not in [c._text for c in shown(view, MemoryItemCard)]


def test_clear_filter(view: MemoryView) -> None:
    view.search.setText("cat")
    view._group_buttons[NOTICED_GROUP].click()

    view.clearFilter()

    assert view._group == ALL
    assert view.filter_bar.isHidden()
    assert len(shown(view, MemoryItemCard)) == 3


def test_delete_emits_entry(view: MemoryView) -> None:
    caught = collect(view.removeRequested)

    shown(view, MemoryItemCard)[1].remove_button.click()

    assert caught[0][0].id == "i2"


def test_edit_emits_correction(view: MemoryView) -> None:
    caught = collect(view.correctRequested)
    card = shown(view, MemoryItemCard)[0]

    card.edit_button.click()
    card.edit.setText("Works on a thesis")
    card.edit_button.click()

    assert caught[0][0].id == "i1"
    assert caught[0][1] == "Works on a thesis"


def test_blank_edit_reverts(view: MemoryView) -> None:
    caught = collect(view.correctRequested)
    card = shown(view, MemoryItemCard)[0]

    card.edit_button.click()
    card.edit.setText("   ")
    card.edit_button.click()

    assert caught == []
    assert card.edit.text() == "Is writing a thesis"


def test_learned_card_undo_and_mark_wrong(view: MemoryView) -> None:
    pattern = Pattern(
        "passed_over_kind",
        (("kind", "remark"),),
        (4, 7, 9),
        "You let my last 3 remarks pass.",
    )
    view.setLearned(
        [Learned("p1", pattern, (Adjustment(FREQUENCY, "1.0", "1.5"),), NOW)]
    )
    undo, wrong = collect(view.undoRequested), collect(view.markWrongRequested)

    (card,) = shown(view, LearnedCard)
    texts = " ".join(w.text() for w in card.findChildren(QLabel))
    card.undo.click()
    card.wrong.click()

    assert "I noticed this 3 times, so I changed how often I start a chat." in texts
    assert undo == [("p1",)] and wrong == [("p1",)]


def test_about_me_why(view: MemoryView, qtbot) -> None:
    view.setFeeling("pleased", "calm")

    texts = " ".join(w.text() for w in view.findChildren(QLabel))
    assert "I feel pleased right now" in texts


def test_moods_off_about_me(view: MemoryView) -> None:
    view.setFeeling("", "")

    texts = " ".join(w.text() for w in view.findChildren(QLabel))
    assert "My moods are switched off" in texts


def test_show_error_hides_the_list(view: MemoryView) -> None:
    view.showError("The remembered items cannot be read.")

    assert shown(view, MemoryItemCard) == []
    assert not view.error.isHidden()
    assert "cannot be read" in view.error.text()


def test_app_minutes_card(view: MemoryView) -> None:
    view.setAppMinutes({"Code.exe": 75})

    texts = " ".join(w.text() for w in view.findChildren(QLabel))
    assert "Time in applications today" in texts
    assert "1 hour 15 minutes" in texts
