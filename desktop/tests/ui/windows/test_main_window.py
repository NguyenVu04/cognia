import pytest

from src.ui.windows.main_window import MainWindow


@pytest.fixture
def window(qtbot) -> MainWindow:
    shown = MainWindow()
    qtbot.addWidget(shown)
    return shown


def test_chat_needs_a_character(window: MainWindow) -> None:
    window.setNeedsCharacter(True)

    window.go("chat")

    assert window.stack.currentWidget() is window.first_run


def test_memory_needs_no_character(window: MainWindow) -> None:
    window.setNeedsCharacter(True)

    window.go("memory")

    assert window.stack.currentIndex() == 0
    assert window.screens.currentWidget() is window.memory


def test_back_from_change_returns_to_character(window: MainWindow) -> None:
    window.showFirstRun()

    window.first_run.backRequested.emit()

    assert window.screens.currentWidget() is window.character
