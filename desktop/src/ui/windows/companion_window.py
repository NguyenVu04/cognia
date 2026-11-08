"""The companion on the desktop.

A frameless window above other windows that never takes the keyboard focus. It
draws the 3D character, which the user can drag anywhere. Hovering shows a
button to hold while talking and a button to hide it. A message it says on its
own appears in a bubble beside it. Hiding or pausing it ends the renderer, so a
hidden companion costs nothing; showing it again loads the character again.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from src.domain.speech.models import ProactiveMessage
from src.domain.tools.models import ActivityStep
from src.ui import theme
from src.ui.widgets.buttons import IconButton
from src.ui.widgets.companion_stage import CompanionStage
from src.ui.widgets.speech_bubble import SpeechBubble
from src.ui.widgets.surface import Panel
from src.ui.widgets.typography import label

WIDTH = 300
HEIGHT = 460
FRAME_LIMIT = 30
_NEVER_FOCUS = (
    Qt.WindowType.Window
    | Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
    | Qt.WindowType.WindowDoesNotAcceptFocus
)
SHOWN = "shown"
HIDDEN = "hidden"
PAUSED = "paused"


def fit_on_screen(position: QPoint, size: tuple[int, int], screen: QRect) -> QPoint:
    """``position`` moved the least distance that puts the whole window inside
    ``screen``."""
    width, height = size
    x = min(max(position.x(), screen.left()), screen.right() - width + 1)
    y = min(max(position.y(), screen.top()), screen.bottom() - height + 1)
    return QPoint(x, y)


class _DragSurface(QWidget):
    """Takes the mouse over the character, which the web view would keep."""

    dragged = Signal(QPoint)
    released = Signal()
    doubleClicked = Signal()
    pointer = Signal(float, float)
    left = Signal()
    entered = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._offset: QPoint | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            self._offset = (
                event.globalPosition().toPoint() - window.frameGeometry().topLeft()
            )
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._offset is not None:
            self.dragged.emit(event.globalPosition().toPoint() - self._offset)
            return
        # Within the window only: the pointer elsewhere is never read.
        x = event.position().x() / max(1, self.width()) * 2 - 1
        y = 1 - event.position().y() / max(1, self.height()) * 2
        self.pointer.emit(x, y)

    def mouseReleaseEvent(self, event) -> None:
        if self._offset is not None:
            self._offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.released.emit()

    def mouseDoubleClickEvent(self, event) -> None:
        self.doubleClicked.emit()

    def enterEvent(self, event) -> None:
        self.entered.emit()

    def leaveEvent(self, event) -> None:
        self.left.emit()


class _TalkButton(IconButton):
    """Held down, it keeps the microphone open."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "microphone",
            "Hold to talk",
            px=18,
            box=38,
            colour=theme.ACCENT_TEXT,
            parent=parent,
        )
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class CompanionWindow(QWidget):
    #: The window was dropped at a new place: x, y and the name of its screen.
    moved = Signal(int, int, str)
    #: An exercise stopped: its name and how many seconds it ran.
    activityEnded = Signal(str, int)
    hideRequested = Signal()
    talkPressed = Signal()
    talkReleased = Signal()
    #: The character cannot be drawn: the reason.
    drawingFailed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, _NEVER_FOCUS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(WIDTH, HEIGHT)
        self._appearance = ""
        self._stage: CompanionStage | None = None
        self._expression = ("neutral", 1.0)
        self._ambient = "active"
        self._activity = ""
        self._steps: tuple[ActivityStep, ...] = ()
        self._step = 0
        self._left = 0
        self._ran = QElapsedTimer()
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._count_down)

        self._holder = QVBoxLayout(self)
        self._holder.setContentsMargins(0, 0, 0, 0)

        self.surface = _DragSurface(self)
        self.surface.setGeometry(0, 0, WIDTH, HEIGHT)
        self.surface.dragged.connect(self.move)
        self.surface.released.connect(self._dropped)
        self.surface.doubleClicked.connect(self.stopActivity)
        self.surface.pointer.connect(lambda x, y: self._call("lookAt", x, y))
        self.surface.left.connect(self._pointer_left)
        self.surface.entered.connect(lambda: self.controls.setVisible(True))

        self.step_label = label("", font=theme.font(14, 700))
        self.step_panel = Panel(
            fill=theme.OVERLAY,
            ring=theme.BORDER,
            radius=12,
            padding=(6, 12, 6, 12),
            parent=self,
        )
        self.step_panel.body().addWidget(self.step_label)
        self.step_panel.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.step_panel.hide()

        self.controls = QWidget(self)
        row = QHBoxLayout(self.controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.talk = _TalkButton()
        self.talk.pressed.connect(self.talkPressed)
        self.talk.released.connect(self.talkReleased)
        row.addWidget(self.talk)
        self.hide_button = IconButton(
            "eye-slash", "Hide from the desktop", px=17, box=38
        )
        self.hide_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide_button.clicked.connect(self.hideRequested)
        row.addWidget(self.hide_button)
        self.controls.adjustSize()
        self.controls.move(
            WIDTH - self.controls.width() - 10, HEIGHT - self.controls.height() - 10
        )
        self.controls.hide()

        self.bubble_window = QWidget(None, _NEVER_FOCUS)
        self.bubble_window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.bubble_window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        bubble_layout = QVBoxLayout(self.bubble_window)
        bubble_layout.setContentsMargins(0, 0, 0, 0)
        self.bubble = SpeechBubble()
        self.bubble.closed.connect(self.hideBubble)
        bubble_layout.addWidget(self.bubble)

    # ── the character ─────────────────────────────────────────────────────

    def setAppearance(self, appearance_id: str) -> None:
        """Draw this character, loading it again if it changed."""
        if appearance_id == self._appearance:
            return
        self._appearance = appearance_id
        if self._stage is not None:
            self._end_stage()
            self._start_stage()

    def setDrawingState(self, drawing: str) -> None:
        """``shown`` draws the character; ``hidden`` and ``paused`` end the
        renderer and take the window off the screen."""
        if drawing == SHOWN:
            if self._stage is None:
                self._start_stage()
            self.show()
            return
        self.stopActivity()
        self.hideBubble()
        self.hide()
        self._end_stage()

    def isDrawing(self) -> bool:
        return self._stage is not None

    def _start_stage(self) -> None:
        if not self._appearance:
            return
        stage = CompanionStage(self._appearance)
        stage.failed.connect(self.drawingFailed)
        self._holder.addWidget(stage)
        self._stage = stage
        stage.call("setFrameLimit", FRAME_LIMIT)
        stage.call("setExpression", *self._expression)
        stage.call("setAmbient", self._ambient)
        self.step_panel.raise_()
        self.surface.raise_()
        self.controls.raise_()

    def _end_stage(self) -> None:
        if self._stage is None:
            return
        self._holder.removeWidget(self._stage)
        self._stage.hide()
        self._stage.deleteLater()
        self._stage = None

    def _call(self, function: str, *args) -> None:
        if self._stage is not None:
            self._stage.call(function, *args)

    # ── what the character shows ──────────────────────────────────────────

    def setExpression(self, preset: str, weight: float) -> None:
        self._expression = (preset, weight)
        self._call("setExpression", preset, weight)

    def setAmbient(self, state: str) -> None:
        """``active``, ``waiting`` or ``dozing``."""
        self._ambient = state
        self._call("setAmbient", state)

    def playGesture(self, name: str) -> None:
        """Play a gesture once. One that arrives while another plays is dropped."""
        self._call("playGesture", name)

    def startThink(self) -> None:
        self._call("startThink")

    def endThink(self) -> None:
        self._call("endThink")

    def setMouth(self, weights: Mapping[str, float]) -> None:
        self._call("setMouth", dict(weights))

    def playActivity(self, name: str, steps: Sequence[ActivityStep]) -> None:
        """Do the exercise ``name`` step by step. It ends when the steps run
        out, or on :meth:`stopActivity`."""
        if not steps:
            return
        self._activity, self._steps, self._step = name, tuple(steps), 0
        self._left = self._steps[0].seconds
        self._ran.start()
        self._tick.start()
        self._show_step()

    def stopActivity(self) -> None:
        """End the exercise now, and say how long it ran."""
        if not self._activity:
            return
        name, seconds = self._activity, int(self._ran.elapsed() // 1000)
        self._tick.stop()
        self._activity, self._steps = "", ()
        self.step_panel.hide()
        self._call("stopActivity")
        self.activityEnded.emit(name, seconds)

    def activity(self) -> str:
        return self._activity

    def stepText(self) -> str:
        return self.step_label.text()

    def _count_down(self) -> None:
        self._left -= 1
        if self._left <= 0:
            self._step += 1
            if self._step >= len(self._steps):
                self.stopActivity()
                return
            self._left = self._steps[self._step].seconds
            self._show_step()
            return
        self._show_label()

    def _show_step(self) -> None:
        self._call("activityStep", self._activity, self._steps[self._step].label)
        self._show_label()

    def _show_label(self) -> None:
        step = self._steps[self._step].label
        self.step_label.setText(f"{step[0].upper()}{step[1:]} · {self._left}")
        self.step_panel.adjustSize()
        self.step_panel.move((WIDTH - self.step_panel.width()) // 2, 12)
        self.step_panel.show()

    # ── the bubble ────────────────────────────────────────────────────────

    def showBubble(self, message: ProactiveMessage) -> None:
        self.bubble.showMessage(message)
        self.bubble_window.adjustSize()
        self._place_bubble()
        self.bubble_window.show()

    def hideBubble(self) -> None:
        self.bubble_window.hide()

    def _place_bubble(self) -> None:
        """Above the character, or below it when there is no room above."""
        size = self.bubble_window.size()
        x = self.x() + (WIDTH - size.width()) // 2
        y = self.y() + 40 - size.height()
        screen = self.screen().availableGeometry()
        if y < screen.top():
            y = self.y() + HEIGHT - 40
        self.bubble_window.move(
            fit_on_screen(QPoint(x, y), (size.width(), size.height()), screen)
        )

    # ── place ─────────────────────────────────────────────────────────────

    def place(self, position: QPoint | None) -> bool:
        """Put the window at ``position``, or at the bottom right of the primary
        screen when there is none. Returns whether it had to move the window
        to keep it wholly on a screen."""
        primary = QGuiApplication.primaryScreen().availableGeometry()
        if position is None:
            self.move(primary.right() - WIDTH - 24, primary.bottom() - HEIGHT - 8)
            return False
        target = QGuiApplication.screenAt(position + QPoint(WIDTH // 2, HEIGHT // 2))
        area = target.availableGeometry() if target is not None else primary
        fitted = fit_on_screen(position, (WIDTH, HEIGHT), area)
        self.move(fitted)
        return fitted != position

    def _dropped(self) -> None:
        if self.bubble_window.isVisible():
            self._place_bubble()
        screen = self.screen()
        self.moved.emit(self.x(), self.y(), screen.name() if screen else "")

    def _pointer_left(self) -> None:
        self._call("lookAt", None, None)
        over = self.controls.geometry().contains(self.mapFromGlobal(QCursor.pos()))
        self.controls.setVisible(over)

    def leaveEvent(self, event) -> None:
        self.controls.setVisible(False)
        super().leaveEvent(event)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self.bubble_window.isVisible():
            self._place_bubble()
