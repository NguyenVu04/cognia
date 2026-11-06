from src.ui.views.proactivity import ProactivityView
from src.ui.widgets.buttons import DashedButton


def test_break_row_preview_emits_nudge(qtbot) -> None:
    view = ProactivityView()
    qtbot.addWidget(view)
    caught: list = []
    view.nudgeRequested.connect(lambda: caught.append(True))

    (preview,) = view.findChildren(DashedButton)
    preview.click()

    assert caught == [True]
