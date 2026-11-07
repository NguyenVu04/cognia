from PySide6.QtWidgets import QLabel

from src.ui.views import sample_data
from src.ui.views.desk import DeskView

SWITCH_NOTE = (
    "It knows if you are at the machine and which application is in front "
    "— never what is inside it."
)


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


def test_reads_names_the_application() -> None:
    assert any("application" in line.casefold() for line in sample_data.READS)


def test_switch_note_names_the_application(qtbot) -> None:
    view = DeskView()
    qtbot.addWidget(view)

    assert SWITCH_NOTE in [child.text() for child in view.findChildren(QLabel)]
