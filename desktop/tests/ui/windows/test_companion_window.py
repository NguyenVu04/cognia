from src.ui.windows.companion_window import GESTURE_MS, CompanionWindow


def test_placeholder_before_anything(qtbot) -> None:
    window = CompanionWindow()
    qtbot.addWidget(window)

    assert window.caption().startswith("anime-style sprite")


def test_expression_caption(qtbot) -> None:
    window = CompanionWindow()
    qtbot.addWidget(window)

    window.setExpression("happy", 0.867)

    assert window.caption() == "happy · 0.87\ndrag me"


def test_gesture_shows_then_clears(qtbot) -> None:
    window = CompanionWindow()
    qtbot.addWidget(window)
    window.setExpression("neutral", 1.0)

    window.playGesture("bow")
    assert "bow" in window.caption()

    qtbot.waitUntil(lambda: "bow" not in window.caption(), timeout=GESTURE_MS + 1000)
    assert window.caption() == "neutral · 1.00\ndrag me"


def test_gesture_replaces_previous(qtbot) -> None:
    window = CompanionWindow()
    qtbot.addWidget(window)

    window.playGesture("bow")
    window.playGesture("nod")

    assert "nod" in window.caption()
    assert "bow" not in window.caption()



def steps():
    from src.domain.tools.models import ActivityStep

    return (ActivityStep("breathe in", 1), ActivityStep("hold", 1))


def test_countdown_caption(qtbot) -> None:
    window = CompanionWindow()
    qtbot.addWidget(window)

    window.playActivity("breathing", steps())

    assert "breathing · breathe in · 1" in window.caption()
    qtbot.waitUntil(lambda: "hold" in window.caption(), timeout=2500)


def test_activity_ends_by_itself(qtbot) -> None:
    window = CompanionWindow()
    qtbot.addWidget(window)
    ended: list[tuple[str, int]] = []
    window.activityEnded.connect(lambda name, seconds: ended.append((name, seconds)))

    window.playActivity("breathing", steps())

    qtbot.waitUntil(lambda: bool(ended), timeout=4000)
    assert ended[0][0] == "breathing"
    assert 1 <= ended[0][1] <= 3
    assert "breathing" not in window.caption()


def test_stop_reports_elapsed(qtbot) -> None:
    window = CompanionWindow()
    qtbot.addWidget(window)
    ended: list[tuple[str, int]] = []
    window.activityEnded.connect(lambda name, seconds: ended.append((name, seconds)))

    window.playActivity("breathing", steps())
    window.stopActivity()
    window.stopActivity()

    assert ended == [("breathing", 0)]
