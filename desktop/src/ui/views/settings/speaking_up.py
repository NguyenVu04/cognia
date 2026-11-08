"""Speaking up: everything the companion does uninvited, on one page.

The companion decides for itself how often to speak. The user can set a daily
ceiling, quiet hours, a break threshold, which kinds of message it may send,
and whether it has moods. Nothing changes until Save; Cancel puts back what is
in force.
"""

from __future__ import annotations

from datetime import time

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QSpinBox, QWidget

from src.domain.speech.models import KIND_LABELS, MessageKind, SpeechSettings
from src.ui import theme
from src.ui.views.settings.common import Section, setting_row
from src.ui.widgets.buttons import Button
from src.ui.widgets.dropdown import Dropdown
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


def _minutes_list(unset: str, values: range) -> Dropdown:
    """A list of minute counts whose first entry means "not set"."""
    box = Dropdown()
    box.addItem(unset, None)
    for value in values:
        box.addItem(f"{value} min", value)
    box.setFixedWidth(150)
    return box


def _choose(box: Dropdown, value: int | None) -> None:
    """Select ``value``, adding it when a stored value is not on the list."""
    index = box.findData(value)
    if index < 0:
        box.addItem(f"{value} min", value)
        index = box.count() - 1
    box.setCurrentIndex(index)


class TimePicker(QWidget):
    """A time of day as an hour list and a minute list."""

    def __init__(self, at: time, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.hour = Dropdown()
        self.hour.addItems([f"{h:02d}" for h in range(24)])
        self.minute = Dropdown()
        self.minute.addItems([f"{m:02d}" for m in range(60)])
        self.hour.setAccessibleName("Hour")
        self.minute.setAccessibleName("Minute")
        row.addWidget(self.hour)
        row.addWidget(caption(":", px=13))
        row.addWidget(self.minute)
        self.setTime(at)

    def time(self) -> time:
        return time(self.hour.currentIndex(), self.minute.currentIndex())

    def setTime(self, at: time) -> None:
        self.hour.setCurrentIndex(at.hour)
        self.minute.setCurrentIndex(at.minute)


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
        self.threshold = _minutes_list("I choose", range(30, 241, 15))
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
        self.quiet_start = TimePicker(time(22, 0))
        self.quiet_end = TimePicker(time(7, 0))
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
        _choose(self.threshold, settings.break_threshold_min)
        self.quiet_on.setChecked(settings.quiet is not None)
        if settings.quiet is not None:
            start, end = settings.quiet
            self.quiet_start.setTime(start)
            self.quiet_end.setTime(end)
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
            quiet = (self.quiet_start.time(), self.quiet_end.time())
        ceiling = self.ceiling.value()
        return SpeechSettings(
            ceiling=None if ceiling < 1 else ceiling,
            quiet=quiet,
            enabled=frozenset(k for k, t in self.kinds.items() if t.isChecked()),
            moods_on=self.moods.isChecked(),
            break_threshold_min=self.threshold.currentData(),
        )

    def _save(self) -> None:
        self.saveRequested.emit(self.edited())

    def _quiet_enabled(self, on: bool) -> None:
        self.quiet_start.setEnabled(on)
        self.quiet_end.setEnabled(on)
