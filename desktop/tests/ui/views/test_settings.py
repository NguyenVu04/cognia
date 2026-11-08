from datetime import datetime, time, timezone

import pytest
from PySide6.QtGui import QKeySequence

from src.domain.speech.models import MessageKind, SpeechSettings
from src.domain.tools.models.tool_server import STDIO, ToolServer
from src.ui.dialogs.add_tool_server_dialog import AddToolServerDialog
from src.ui.views.settings.view import SettingsView
from src.ui.views.settings.voice import NEEDS_MODIFIER, usable
from src.ui.widgets.buttons import Button


@pytest.fixture
def view(qtbot) -> SettingsView:
    shown = SettingsView()
    qtbot.addWidget(shown)
    return shown


def collect(signal) -> list:
    caught: list = []
    signal.connect(lambda *args: caught.append(args))
    return caught


def test_six_sections(view: SettingsView) -> None:
    for section in ("speaking", "desk", "voice", "tools", "startup", "erase"):
        view.openSection(section)
        assert view.currentSection() == section


def test_speaking_up_save_emits_the_page(view: SettingsView) -> None:
    page = view.speaking_up
    caught = collect(page.saveRequested)

    page.ceiling.setValue(3)
    page.kinds[MessageKind.REMARK].setChecked(False)
    page.save.click()

    (chosen,) = caught[0]
    assert chosen.ceiling == 3
    assert MessageKind.REMARK not in chosen.enabled
    assert chosen.quiet is None


def test_speaking_up_cancel_restores(view: SettingsView) -> None:
    page = view.speaking_up
    in_force = SpeechSettings(None, (time(22, 0), time(7, 0)), frozenset(MessageKind),
                              True, None)
    page.setSettings(in_force)

    page.ceiling.setValue(5)
    page.cancel.click()

    assert page.edited() == in_force


def test_no_limit_reads_as_none(view: SettingsView) -> None:
    page = view.speaking_up
    page.setSettings(SpeechSettings.defaults())

    assert page.ceiling.text() == "No limit"
    assert page.edited().ceiling is None


def test_quiet_hours_chosen_from_hour_and_minute_lists(view: SettingsView) -> None:
    page = view.speaking_up
    page.setSettings(SpeechSettings.defaults())
    assert not page.quiet_start.hour.isEnabled()

    page.quiet_on.setChecked(True)
    page.quiet_start.hour.setCurrentText("23")
    page.quiet_start.minute.setCurrentText("15")
    page.quiet_end.hour.setCurrentText("06")
    page.quiet_end.minute.setCurrentText("45")

    assert page.quiet_start.hour.isEnabled()
    assert page.edited().quiet == (time(23, 15), time(6, 45))


def test_break_threshold_list(view: SettingsView) -> None:
    page = view.speaking_up
    page.setSettings(SpeechSettings.defaults())
    assert page.threshold.currentText() == "I choose"
    assert page.edited().break_threshold_min is None

    page.threshold.setCurrentText("90 min")

    assert page.edited().break_threshold_min == 90


def test_stored_threshold_off_the_list_is_kept(view: SettingsView) -> None:
    page = view.speaking_up
    stored = SpeechSettings(None, None, frozenset(MessageKind), True, 37)

    page.setSettings(stored)

    assert page.edited().break_threshold_min == 37


def test_save_failure_shows_the_sentence(view: SettingsView) -> None:
    view.speaking_up.showError("The setting could not be saved.")

    assert not view.speaking_up.error.isHidden()


def test_desk_exclude_and_off_hides_today(view: SettingsView) -> None:
    desk = view.desk
    caught = collect(desk.excludeRequested)

    desk.setAwareness(True)
    desk.name.setText("Steam.exe")
    desk._exclude_typed()
    desk.setAwareness(False)

    assert caught == [("Steam.exe",)]
    assert desk.today.isHidden()


def test_hotkey_needs_a_modifier(view: SettingsView) -> None:
    assert usable(QKeySequence("Ctrl+Alt+Space"))
    assert not usable(QKeySequence("Space"))

    view.voice.key.setKeySequence(QKeySequence("K"))
    view.voice._apply()

    assert NEEDS_MODIFIER in view.voice.error.text()


def test_hotkey_chosen(view: SettingsView) -> None:
    caught = collect(view.voice.hotkeyChosen)

    view.voice.key.setKeySequence(QKeySequence("Ctrl+Shift+K"))
    view.voice._apply()

    assert caught == [("Ctrl+Shift+K",)]


def test_tools_list_and_remove(view: SettingsView) -> None:
    at = datetime(2026, 11, 9, tzinfo=timezone.utc)
    caught = collect(view.tools.removeRequested)

    view.tools.setServers([ToolServer("s1", "notes", STDIO, "uvx", (), "", at, at)])
    (remove,) = [b for b in view.tools.findChildren(Button) if b.text() == "Remove"]
    remove.click()

    assert caught == [("s1",)]


def test_add_on_needs_consent(qtbot) -> None:
    dialog = AddToolServerDialog()
    qtbot.addWidget(dialog)

    dialog.name.setText("notes")
    dialog.command.setText("uvx notes-mcp --dir C:/notes")
    assert not dialog.add.isEnabled()
    dialog.consent.setChecked(True)

    assert dialog.add.isEnabled()
    assert dialog.draft().args == ("notes-mcp", "--dir", "C:/notes")


def test_add_on_by_url_needs_http(qtbot) -> None:
    dialog = AddToolServerDialog()
    qtbot.addWidget(dialog)
    dialog.transport.setCurrentIndex(1)
    dialog.name.setText("web")
    dialog.consent.setChecked(True)

    dialog.url.setText("ftp://x")
    assert not dialog.add.isEnabled()
    dialog.url.setText("http://127.0.0.1:8000/mcp")
    assert dialog.add.isEnabled()


def test_erase_levels(view: SettingsView) -> None:
    caught = collect(view.erase.eraseRequested)

    for button in view.erase.findChildren(Button):
        button.click()

    assert caught == [("memory",), ("everything",)]
