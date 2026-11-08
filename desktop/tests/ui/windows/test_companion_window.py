from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from src.domain.tools.models import ActivityStep
from src.ui.windows import companion_window
from src.ui.windows.companion_window import (
    HIDDEN,
    PAUSED,
    SHOWN,
    CompanionWindow,
    fit_on_screen,
)


class FakeStage(QWidget):
    """Stands in for the web view, which needs a GPU."""

    made: list = []

    def __init__(self, appearance_id: str) -> None:
        super().__init__()
        self.appearance_id = appearance_id
        self.calls: list[tuple] = []
        FakeStage.made.append(self)

    failed = property(lambda self: _Signal())

    def call(self, function: str, *args) -> None:
        self.calls.append((function, *args))


class _Signal:
    def connect(self, _slot) -> None:
        pass


def window(qtbot, monkeypatch) -> CompanionWindow:
    FakeStage.made = []
    monkeypatch.setattr(companion_window, "CompanionStage", FakeStage)
    shown = CompanionWindow()
    qtbot.addWidget(shown)
    shown.setAppearance("yuna")
    return shown


def test_never_takes_focus(qtbot, monkeypatch) -> None:
    shown = window(qtbot, monkeypatch)

    assert shown.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert shown.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert shown.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_shown_draws_and_hidden_ends_the_renderer(qtbot, monkeypatch) -> None:
    shown = window(qtbot, monkeypatch)

    shown.setDrawingState(SHOWN)
    assert shown.isDrawing()
    shown.setDrawingState(HIDDEN)
    assert not shown.isDrawing()
    shown.setDrawingState(SHOWN)
    shown.setDrawingState(PAUSED)
    assert not shown.isDrawing()
    assert len(FakeStage.made) == 2


def test_state_replayed_on_a_new_stage(qtbot, monkeypatch) -> None:
    shown = window(qtbot, monkeypatch)
    shown.setExpression("happy", 0.7)
    shown.setAmbient("dozing")

    shown.setDrawingState(SHOWN)

    calls = FakeStage.made[-1].calls
    assert ("setExpression", "happy", 0.7) in calls
    assert ("setAmbient", "dozing") in calls


def test_gesture_reaches_the_page(qtbot, monkeypatch) -> None:
    shown = window(qtbot, monkeypatch)
    shown.setDrawingState(SHOWN)

    shown.playGesture("nod")
    shown.startThink()
    shown.endThink()

    calls = FakeStage.made[-1].calls
    assert ("playGesture", "nod") in calls
    assert ("startThink",) in calls and ("endThink",) in calls


def test_exercise_steps_and_stop(qtbot, monkeypatch) -> None:
    shown = window(qtbot, monkeypatch)
    shown.setDrawingState(SHOWN)
    ended: list = []
    shown.activityEnded.connect(lambda name, seconds: ended.append(name))

    shown.playActivity("breathing", (ActivityStep("breathe in", 4),))
    assert ("activityStep", "breathing", "breathe in") in FakeStage.made[-1].calls
    assert shown.stepText().startswith("Breathe in")
    shown.stopActivity()

    assert ended == ["breathing"]
    assert ("stopActivity",) in FakeStage.made[-1].calls


def test_drag_moves_and_reports_on_release(qtbot, monkeypatch) -> None:
    shown = window(qtbot, monkeypatch)
    shown.move(100, 100)
    moved: list = []
    shown.moved.connect(lambda x, y, screen: moved.append((x, y)))

    surface = shown.surface
    surface.dragged.emit(QPoint(140, 160))
    surface.released.emit()

    assert moved == [(140, 160)]


def test_double_click_stops_exercise(qtbot, monkeypatch) -> None:
    shown = window(qtbot, monkeypatch)
    ended: list = []
    shown.activityEnded.connect(lambda name, seconds: ended.append(name))
    shown.playActivity("stretch", (ActivityStep("reach up", 20),))

    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick, QPointF(10, 10), QPointF(10, 10),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    shown.surface.mouseDoubleClickEvent(event)

    assert ended == ["stretch"]


def test_talk_button_press_and_release(qtbot, monkeypatch) -> None:
    shown = window(qtbot, monkeypatch)
    seen: list[str] = []
    shown.talkPressed.connect(lambda: seen.append("down"))
    shown.talkReleased.connect(lambda: seen.append("up"))

    shown.talk.pressed.emit()
    shown.talk.released.emit()

    assert seen == ["down", "up"]


def test_fit_on_screen_moves_the_least() -> None:
    screen = QRect(0, 0, 1920, 1080)

    assert fit_on_screen(QPoint(100, 100), (300, 460), screen) == QPoint(100, 100)
    assert fit_on_screen(QPoint(1800, 900), (300, 460), screen) == QPoint(1620, 620)
    assert fit_on_screen(QPoint(-50, -20), (300, 460), screen) == QPoint(0, 0)


def test_place_off_screen_is_corrected(qtbot, monkeypatch) -> None:
    shown = window(qtbot, monkeypatch)

    assert shown.place(QPoint(-5000, -5000)) is True
    assert shown.place(None) is False
