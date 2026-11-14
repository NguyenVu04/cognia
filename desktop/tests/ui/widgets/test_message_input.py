import pytest
from PySide6.QtCore import Qt

from src.ui import theme
from src.ui.widgets.message_input import MAX_LINES, MessageInput


@pytest.fixture
def box(qtbot) -> MessageInput:
    shown = MessageInput()
    qtbot.addWidget(shown)
    shown.setFont(theme.font(14.5))
    shown.resize(400, shown.height())
    shown.show()
    return shown


def collect(signal) -> list:
    caught: list = []
    signal.connect(lambda *args: caught.append(args))
    return caught


def test_enter_submits_and_adds_no_line(box: MessageInput, qtbot) -> None:
    submitted = collect(box.submitted)
    qtbot.keyClicks(box, "hello")

    qtbot.keyClick(box, Qt.Key.Key_Return)

    assert len(submitted) == 1
    assert box.text() == "hello"


def test_shift_enter_adds_line(box: MessageInput, qtbot) -> None:
    submitted = collect(box.submitted)
    qtbot.keyClicks(box, "one")

    qtbot.keyClick(box, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    qtbot.keyClicks(box, "two")

    assert submitted == []
    assert box.text() == "one\ntwo"


def test_escape_is_reported(box: MessageInput, qtbot) -> None:
    escaped = collect(box.escaped)

    qtbot.keyClick(box, Qt.Key.Key_Escape)

    assert len(escaped) == 1


def test_typing_is_an_edit_and_set_text_is_not(box: MessageInput, qtbot) -> None:
    edited = collect(box.edited)

    box.setText("from the application")
    box.clear()
    assert edited == []

    qtbot.keyClicks(box, "a")
    assert len(edited) == 1


def test_grows_to_five_lines_then_scrolls(box: MessageInput) -> None:
    box.setText("one")
    one = box.height()
    box.setText("one\ntwo")
    two = box.height()
    box.setText("\n".join(["line"] * MAX_LINES))
    five = box.height()
    box.setText("\n".join(["line"] * (MAX_LINES + 3)))
    eight = box.height()

    assert one < two < five
    assert eight == five
    assert box.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_shrinks_again_when_cleared(box: MessageInput) -> None:
    box.setText("one")
    one = box.height()
    box.setText("one\ntwo\nthree")

    box.clear()

    assert box.height() == one
    assert box.text() == ""
