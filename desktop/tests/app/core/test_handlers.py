"""The new handlers of the core thread, driven through the bridge with a clock
the test moves."""

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from src.app.bridge import Bridge
from src.app.commands import (
    AddToolServer,
    ChooseCharacter,
    ExcludeApp,
    ExplainFeeling,
    OfferCharacters,
    Pause,
    RateMessage,
    RemoveToolServer,
    Resume,
    SaveSpeechSettings,
    SendMessage,
    SetHotkey,
    SetKind,
    SetSpeakAloud,
    Stop,
    WindowOpened,
    Worded,
)
from src.app.core_host import CoreHost
from src.domain.memory.models import Calibration
from src.domain.speech.models import MessageKind, SpeechSettings

SIGNALS = (
    "ready", "screenRequested", "pauseChanged", "speechSettingsShown",
    "speechSettingsSaved", "greetingShown", "askWord", "messageAppended",
    "voiceSettingsShown", "toolServersShown", "toolServersFailed", "deskShown",
    "feelingExplained", "feelingShown", "templatesShown", "noticeShown",
    "addOnsChanged", "placementShown", "closeHintShown", "learnedShown",
)
START = datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class Recorder:
    def __init__(self, bridge: Bridge) -> None:
        self.seen: list[tuple[str, tuple]] = []
        self._changed = threading.Condition()
        for name in SIGNALS:
            getattr(bridge, name).connect(
                lambda *args, name=name: self._add(name, args),
                Qt.ConnectionType.DirectConnection,
            )

    def _add(self, name: str, args: tuple) -> None:
        with self._changed:
            self.seen.append((name, args))
            self._changed.notify_all()

    def all(self, name: str) -> list[tuple]:
        with self._changed:
            return [args for seen, args in self.seen if seen == name]

    def wait(self, name: str, count: int = 1, timeout: float = 10) -> tuple:
        with self._changed:
            done = self._changed.wait_for(
                lambda: len([s for s, _ in self.seen if s == name]) >= count, timeout
            )
        assert done, f"{name} #{count} never came; seen {[s for s, _ in self.seen]}"
        return self.all(name)[count - 1]


@dataclass(frozen=True)
class Core:
    bridge: Bridge
    recorder: Recorder
    clock: Clock
    path: Path

    def send(self, command) -> None:
        self.bridge.send(command)

    def barrier(self) -> None:
        count = len(self.recorder.all("templatesShown")) + 1
        self.send(OfferCharacters())
        self.recorder.wait("templatesShown", count)

    def rows(self, sql: str) -> list[tuple]:
        connection = sqlite3.connect(self.path)
        result = connection.execute(sql).fetchall()
        connection.close()
        return result


@pytest.fixture
def core(qapp, tmp_path: Path):
    bridge = Bridge()
    recorder = Recorder(bridge)
    clock = Clock()
    path = tmp_path / "cognia.sqlite3"
    host = CoreHost(
        path, bridge, calibration=Calibration(0.45, 0.95), history_max_chars=9700,
        embedding_identity=None, device_loaded=lambda name: None, clock=clock,
    )
    host.start()
    recorder.wait("ready")
    yield Core(bridge, recorder, clock, path)
    bridge.send(Stop())
    host.join(5)


def choose(core: Core) -> None:
    core.send(ChooseCharacter("yuna"))
    core.recorder.wait("screenRequested")


# ── pause ─────────────────────────────────────────────────────────────────


def test_pause_records_and_resume_says_how_long(core: Core) -> None:
    core.send(Pause(START + timedelta(hours=1)))
    assert core.recorder.wait("pauseChanged", 2) == (True, "until 10:00", "")

    core.clock.now = START + timedelta(minutes=45)
    core.send(Resume())

    assert core.recorder.wait("pauseChanged", 3) == (False, "", "45 minutes")
    assert core.rows("SELECT kind FROM events WHERE kind IN ('paused', 'resumed')") \
        == [("paused",), ("resumed",)]
    assert core.rows("SELECT paused_at FROM settings") == [(None,)]


def test_pause_ends_by_itself(core: Core) -> None:
    core.send(Pause(START + timedelta(hours=1)))
    core.recorder.wait("pauseChanged", 2)

    core.clock.now = START + timedelta(hours=1, seconds=1)
    core.barrier()

    paused, _, lasted = core.recorder.wait("pauseChanged", 3)
    assert (paused, lasted) == (False, "1 hour")


def test_pause_until_resumed_has_no_end(core: Core) -> None:
    core.send(Pause(None))

    assert core.recorder.wait("pauseChanged", 2) == (True, "until you resume", "")


# ── the greeting ──────────────────────────────────────────────────────────


def test_greeting_once_a_day(core: Core) -> None:
    choose(core)
    core.send(WindowOpened())
    (job,) = core.recorder.wait("askWord")
    assert "Greet the user" in job.instruction

    core.send(Worded(job.job_id, "Good morning! Nothing needs your attention."))
    message, note = core.recorder.wait("greetingShown")
    core.send(WindowOpened())
    core.barrier()

    assert message.text == "Good morning! Nothing needs your attention."
    assert "Nothing needs your attention." in note
    assert len(core.recorder.all("askWord")) == 1
    assert core.rows("SELECT kind, outcome FROM speech_decisions") \
        == [("greeting", "sent")]


def test_greeting_without_words_uses_plain_words(core: Core) -> None:
    choose(core)
    core.send(WindowOpened())
    (job,) = core.recorder.wait("askWord")

    core.send(Worded(job.job_id, ""))

    message, _ = core.recorder.wait("greetingShown")
    assert message.text == "Good to see you. Nothing needs your attention."


def test_no_greeting_without_a_character(core: Core) -> None:
    core.send(WindowOpened())
    core.barrier()

    assert core.recorder.all("askWord") == []


# ── speaking up ───────────────────────────────────────────────────────────


def test_dont_send_this_kind_is_immediate(core: Core) -> None:
    core.send(SetKind(MessageKind.REMARK, False))

    (settings,) = core.recorder.wait("speechSettingsShown", 2)
    assert MessageKind.REMARK not in settings.enabled


def test_save_speech_settings(core: Core) -> None:
    chosen = SpeechSettings(4, None, frozenset({MessageKind.BREAK}), True, 60)

    core.send(SaveSpeechSettings(chosen))

    assert core.recorder.wait("speechSettingsSaved") == ("",)
    assert core.rows("SELECT daily_ceiling, break_threshold_min FROM settings") \
        == [(4, 60)]


def test_switching_moods_off_is_an_event(core: Core) -> None:
    choose(core)
    chosen = SpeechSettings(None, None, frozenset(MessageKind), False, None)

    core.send(SaveSpeechSettings(chosen))
    core.recorder.wait("speechSettingsSaved")

    assert ("setting_changed",) in core.rows("SELECT kind FROM events")


# ── the conversation ──────────────────────────────────────────────────────


def test_rating_writes_the_column_and_an_event(core: Core) -> None:
    choose(core)
    core.send(SendMessage("hello"))
    (message,) = core.recorder.wait("messageAppended")

    core.send(RateMessage(message.id, -1))
    core.barrier()

    assert core.rows("SELECT rating FROM messages") == [(-1,)]
    assert ("message_rated",) in core.rows("SELECT kind FROM events")


def test_explain_feeling(core: Core) -> None:
    choose(core)

    core.send(ExplainFeeling())

    name, found = core.recorder.wait("feelingExplained")
    assert name == "Yuna"
    assert found.feeling == "calm"


# ── settings ──────────────────────────────────────────────────────────────


def test_voice_settings(core: Core) -> None:
    assert core.recorder.wait("voiceSettingsShown") == (True, "Ctrl+Alt+Space")

    core.send(SetSpeakAloud(False))
    core.send(SetHotkey("Ctrl+Shift+K"))

    assert core.recorder.wait("voiceSettingsShown", 3) == (False, "Ctrl+Shift+K")


def test_add_and_remove_an_add_on(core: Core) -> None:
    core.send(AddToolServer("notes", "stdio", "uvx", ("notes",), ""))
    (servers,) = core.recorder.wait("toolServersShown", 2)

    core.send(RemoveToolServer(servers[0].id))

    assert servers[0].name == "notes"
    assert core.recorder.wait("toolServersShown", 3) == ([],)
    assert core.recorder.wait("addOnsChanged", 3) == ([],)


def test_add_on_without_a_command_is_refused(core: Core) -> None:
    core.send(AddToolServer("notes", "stdio", "", (), ""))

    (error,) = core.recorder.wait("toolServersFailed")
    assert "command" in error


def test_exclude_an_application(core: Core) -> None:
    core.send(ExcludeApp("Steam.exe"))

    _, _, excluded = core.recorder.wait("deskShown", 2)
    assert excluded == ["Steam.exe"]
    assert core.rows("SELECT app_name FROM app_exclusions") == [("Steam.exe",)]
