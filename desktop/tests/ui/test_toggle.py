from src.ui.widgets.toggle import PillToggle


def test_small_toggle_size(qtbot) -> None:
    toggle = PillToggle("small", checked=False)
    qtbot.addWidget(toggle)

    assert (toggle.width(), toggle.height()) == (46, 26)
    assert not toggle.isChecked()
