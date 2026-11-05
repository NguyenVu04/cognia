from src.ui.widgets.spinner import SIZE, Spinner


def test_turns_only_while_shown(qtbot) -> None:
    spinner = Spinner()
    qtbot.addWidget(spinner)

    spinner.show()
    shown = spinner.turning
    spinner.hide()

    assert shown is True
    assert spinner.turning is False


def test_draws_at_its_size(qtbot) -> None:
    spinner = Spinner()
    qtbot.addWidget(spinner)

    image = spinner.grab()

    assert (image.width(), image.height()) == (SIZE, SIZE)
