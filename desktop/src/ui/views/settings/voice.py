"""Voice: whether replies are said aloud, and the key combination for talking."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QKeySequenceEdit, QWidget

from src.ui import theme
from src.ui.views.settings.common import Section, setting_row
from src.ui.widgets.buttons import Button
from src.ui.widgets.toggle import PillToggle
from src.ui.widgets.typography import caption

NEEDS_MODIFIER = "Add Ctrl, Alt or Win so it doesn't get in the way of typing."
_MODIFIERS = (
    Qt.KeyboardModifier.ControlModifier
    | Qt.KeyboardModifier.AltModifier
    | Qt.KeyboardModifier.MetaModifier
)


def usable(sequence: QKeySequence) -> bool:
    """Whether ``sequence`` is one key held with at least one of Ctrl, Alt or
    Win."""
    if sequence.count() != 1:
        return False
    return bool(sequence[0].keyboardModifiers() & _MODIFIERS)


class VoiceSection(Section):
    speakAloudToggled = Signal(bool)
    hotkeyChosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Voice",
            "Talk to me instead of typing, and hear me answer. I only listen "
            "while you're talking, and I never keep recordings. (English only "
            "for now.)",
            parent,
        )
        speak = self.card()
        self.speak = PillToggle("large")
        self.speak.clicked.connect(
            lambda: self.speakAloudToggled.emit(self.speak.isChecked())
        )
        speak.body().addWidget(
            setting_row(
                "Say replies aloud",
                "In my own voice. Start typing anytime to stop me.",
                self.speak,
            )[0]
        )

        key = self.card()
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        self.key = QKeySequenceEdit()
        self.key.setMaximumSequenceLength(1)
        self.key.setFixedWidth(170)
        self.key.setFont(theme.font(13.5))
        row.addWidget(self.key)
        apply = Button("Use", size="small")
        apply.clicked.connect(self._apply)
        row.addWidget(apply)
        key.body().addWidget(
            setting_row(
                "Talk key",
                "Press it anywhere to start talking, and again when "
                "you're done. You'll see the words before they're sent.",
                holder,
            )[0]
        )
        self.status = caption("")
        self.status.setWordWrap(True)
        self.column.addWidget(self.status)

    def setSpeakAloud(self, on: bool) -> None:
        self.speak.setChecked(on)

    def setHotkey(self, sequence: str) -> None:
        self.key.setKeySequence(QKeySequence(sequence))

    def setStatus(self, text: str) -> None:
        self.status.setText(text)

    def _apply(self) -> None:
        sequence = self.key.keySequence()
        if not usable(sequence):
            self.showError(NEEDS_MODIFIER)
            return
        self.showError("")
        self.hotkeyChosen.emit(
            sequence.toString(QKeySequence.SequenceFormat.PortableText)
        )
