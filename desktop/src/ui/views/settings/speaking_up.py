"""Speaking up: everything the companion does uninvited, on one page.

The companion decides for itself how often to speak. The user can set a daily
ceiling, quiet hours, a break threshold, which kinds of message it may send,
and whether it has moods. Nothing changes until Save; Cancel puts back what is
in force.
"""

from __future__ import annotations

from datetime import time

from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QSpinBox, QTimeEdit, QWidget

from src.domain.speech.models import KIND_LABELS, MessageKind, SpeechSettings
from src.ui import theme
from src.ui.views.settings.common import Section, setting_row
from src.ui.widgets.buttons import Button
from src.ui.widgets.toggle import PillToggle
from src.ui.widgets.typography import caption, kicker

NO_LIMIT = "No limit"


def _optional_box(suffix: str, low: int, high: int) -> QSpinBox:
    """A number box whose lowest value means "not set"."""
    box = QSpinBox()
    box.setRange(low - 1, high)
    box.setSpecialValueText(NO_LIMIT)
    box.setSuffix(suffix)
    box.setFont(theme.font(13.5))
    box.setFixedWidth(150)
    return box


class SpeakingUpSection(Section):
    saveRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Speaking up",
            "I choose my moments to chat, and I never interrupt while you're "
            "typing, presenting or away. You can set gentle limits here.",
            parent,
        )
        self._in_force = SpeechSettings.defaults()

        limits = self.card()
        self.ceiling = _optional_box(" a day", 1, 50)
        limits.body().addWidget(
            setting_row(
                "Daily limit",
                "How many times a day I may start a chat. My hello doesn't count.",
                self.ceiling,
            )[0]
        )
        limits.body().addSpacing(12)
        self.threshold = _optional_box(" min", 30, 240)
        self.threshold.setSpecialValueText("I choose")
        limits.body().addWidget(
            setting_row(
                "Break threshold",
                "How long before I suggest a break. Leave it to me "
                "and I'll pick a time that feels right.",
                self.threshold,
            )[0]
        )
        limits.body().addSpacing(12)
        quiet = QWidget()
        quiet_row = QHBoxLayout(quiet)
        quiet_row.setContentsMargins(0, 0, 0, 0)
        self.quiet_on = QCheckBox("From")
        self.quiet_on.setFont(theme.font(13.5))
        self.quiet_start = QTimeEdit(QTime(22, 0))
        self.quiet_end = QTimeEdit(QTime(7, 0))
        for edit in (self.quiet_start, self.quiet_end):
            edit.setDisplayFormat("HH:mm")
            edit.setFont(theme.font(13.5))
        quiet_row.addWidget(self.quiet_on)
        quiet_row.addWidget(self.quiet_start)
        quiet_row.addWidget(caption("to", px=13))
        quiet_row.addWidget(self.quiet_end)
        self.quiet_on.toggled.connect(self._quiet_enabled)
        limits.body().addWidget(
            setting_row("Quiet hours", "Times when I won't start a chat.", quiet)[0]
        )

        kinds = self.card()
        kinds.body().addWidget(kicker("What I may say on my own"))
        kinds.body().addSpacing(8)
        self.kinds: dict[MessageKind, PillToggle] = {}
        for kind, (title, detail) in KIND_LABELS.items():
            toggle = PillToggle("small")
            self.kinds[kind] = toggle
            kinds.body().addWidget(setting_row(title, detail, toggle)[0])
            kinds.body().addSpacing(6)

        moods = self.card()
        self.moods = PillToggle("small")
        moods.body().addWidget(
            setting_row(
                "Moods",
                "Turn this off and I'll stay even-tempered all the time.",
                self.moods,
            )[0]
        )

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.save = Button("Save", variant="primary", icon_name="check")
        self.save.clicked.connect(self._save)
        buttons.addWidget(self.save)
        self.cancel = Button("Cancel")
        self.cancel.clicked.connect(lambda: self.setSettings(self._in_force))
        buttons.addWidget(self.cancel)
        self.saved = caption("")
        buttons.addWidget(self.saved)
        buttons.addStretch(1)
        self.column.addLayout(buttons)
        self.setSettings(self._in_force)

    def setSettings(self, settings: SpeechSettings) -> None:
        """Show the settings in force, discarding unsaved changes."""
        self._in_force = settings
        self.ceiling.setValue(settings.ceiling or self.ceiling.minimum())
        self.threshold.setValue(
            settings.break_threshold_min or self.threshold.minimum()
        )
        self.quiet_on.setChecked(settings.quiet is not None)
        if settings.quiet is not None:
            start, end = settings.quiet
            self.quiet_start.setTime(QTime(start.hour, start.minute))
            self.quiet_end.setTime(QTime(end.hour, end.minute))
        self._quiet_enabled(settings.quiet is not None)
        for kind, toggle in self.kinds.items():
            toggle.setChecked(kind in settings.enabled)
        self.moods.setChecked(settings.moods_on)
        self.saved.setText("")
        self.showError("")

    def showSaved(self) -> None:
        self.saved.setText("Saved. In force from the next decision to speak.")

    def edited(self) -> SpeechSettings:
        """The settings as they stand on the page."""
        quiet = None
        if self.quiet_on.isChecked():
            start, end = self.quiet_start.time(), self.quiet_end.time()
            quiet = (time(start.hour(), start.minute()), time(end.hour(), end.minute()))
        ceiling = self.ceiling.value()
        threshold = self.threshold.value()
        return SpeechSettings(
            ceiling=None if ceiling < 1 else ceiling,
            quiet=quiet,
            enabled=frozenset(k for k, t in self.kinds.items() if t.isChecked()),
            moods_on=self.moods.isChecked(),
            break_threshold_min=None if threshold < 30 else threshold,
        )

    def _save(self) -> None:
        self.saveRequested.emit(self.edited())

    def _quiet_enabled(self, on: bool) -> None:
        self.quiet_start.setEnabled(on)
        self.quiet_end.setEnabled(on)
