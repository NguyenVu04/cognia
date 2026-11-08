import pytest
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut

from src.ui.views.navigation import CHARACTER, COMPANION, MEMORY, SETTINGS
from src.ui.windows.main_window import MainWindow


@pytest.fixture
def window(qtbot) -> MainWindow:
    shown = MainWindow()
    qtbot.addWidget(shown)
    return shown


def test_companion_needs_a_character(window: MainWindow) -> None:
    window.setNeedsCharacter(True)

    window.go(COMPANION)

    assert window.stack.currentWidget() is window.first_run


def test_memory_needs_no_character(window: MainWindow) -> None:
    window.setNeedsCharacter(True)

    window.go(MEMORY)

    assert window.stack.currentIndex() == 0
    assert window.screens.currentWidget() is window.memory


def test_four_screens_only(window: MainWindow) -> None:
    assert set(window._by_id) == {COMPANION, MEMORY, CHARACTER, SETTINGS}


def test_back_from_change_returns_to_character(window: MainWindow) -> None:
    window.showFirstRun()

    window.first_run.backRequested.emit()

    assert window.screens.currentWidget() is window.character


def test_ctrl_2_opens_memory(window: MainWindow) -> None:
    (shortcut,) = [
        s for s in window.findChildren(QShortcut)
        if s.key() == QKeySequence("Ctrl+2")
    ]

    shortcut.activated.emit()

    assert window.screens.currentWidget() is window.memory


def test_close_hides_instead_of_quitting(window: MainWindow, qtbot) -> None:
    event = QCloseEvent()
    with qtbot.waitSignal(window.closeRequested):
        window.closeEvent(event)

    assert not event.isAccepted()


def test_close_allowed_when_quitting(window: MainWindow) -> None:
    window.allowClose()
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted()


def test_onboarding_steps(window: MainWindow) -> None:
    window.showOnboarding()
    assert window.stack.currentWidget() is window.desk_step

    window.showTips()
    window.tips_step.done.emit()

    assert window.screens.currentWidget() is window.chat


def test_open_settings_section(window: MainWindow) -> None:
    window.openSettings("voice")

    assert window.screens.currentWidget() is window.settings
    assert window.settings.currentSection() == "voice"


def test_loading_spinner_shows_and_hides(window: MainWindow) -> None:
    window.setLoading(True)
    shown = not window.loading.isHidden()
    window.setLoading(False)

    assert shown
    assert window.loading.isHidden()
