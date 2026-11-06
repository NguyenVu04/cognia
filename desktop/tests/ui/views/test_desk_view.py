from src.ui.views import sample_data
from src.ui.views.desk import DeskView


def test_off_until_switched_on(qtbot) -> None:
    view = DeskView()
    qtbot.addWidget(view)

    assert view.toggle.isChecked() is False
    assert view.state_label.text() == "Desk awareness is off"


def test_click_asks_for_the_change(qtbot) -> None:
    view = DeskView()
    qtbot.addWidget(view)
    asked: list[bool] = []
    view.awarenessToggled.connect(asked.append)

    view.toggle.click()

    assert asked == [True]


def test_set_awareness_does_not_ask(qtbot) -> None:
    view = DeskView()
    qtbot.addWidget(view)
    asked: list[bool] = []
    view.awarenessToggled.connect(asked.append)

    view.setAwareness(True)

    assert asked == []
    assert view.state_label.text() == "Desk awareness is on"


def test_error_shown_and_hidden(qtbot) -> None:
    view = DeskView()
    qtbot.addWidget(view)

    view.showError("Cannot read.")
    assert not view.error.isHidden()
    assert view.error.text() == "Cannot read."

    view.showError("")
    assert view.error.isHidden()


def test_never_reads_no_longer_claims_the_application() -> None:
    assert not any("application" in line.casefold() for line in sample_data.NEVER_READS)
