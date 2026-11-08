import ctypes
import struct
from ctypes import wintypes

import httpx
import pytest
from PySide6.QtCore import QByteArray, QObject
from PySide6.QtMultimedia import QtAudio
from shiboken6 import VoidPtr

from src.infrastructure.voice import microphone, mouth
from src.infrastructure.voice.hotkey import WM_HOTKEY, TalkHotkey, _Filter, parse
from src.infrastructure.voice.microphone import level, silence_ended, wav
from src.infrastructure.voice.sentences import split_ready
from src.infrastructure.voice.speaker import Clip, Speaker, pcm16
from src.infrastructure.voice.transcriber import (
    SpeechUnavailable,
    Transcriber,
    TranscriptionServer,
    clean,
)

# ── mouth ─────────────────────────────────────────────────────────────────


def test_hello_shapes() -> None:
    timings = [
        ("h", 0.0, 0.05),
        ("ə", 0.05, 0.11),
        ("l", 0.11, 0.16),
        ("ˈ", 0.16, 0.18),
        ("o", 0.18, 0.25),
        ("ʊ", 0.25, 0.3),
    ]

    shapes = [(s.shape, round(s.weight, 2)) for s in mouth.spans(timings)]

    assert shapes == [
        ("", 0.0),
        ("aa", 0.4),
        ("aa", 0.2),
        ("aa", 0.4),
        ("oh", 0.8),
        ("ou", 0.7),
    ]


def test_lips_close_on_m() -> None:
    (span,) = mouth.spans([("m", 0.0, 0.1)])

    assert (span.shape, span.weight) == ("", 0.0)


def test_quiet_audio_opens_the_mouth_less() -> None:
    spans = mouth.spans([("a", 0.0, 0.1)])
    loud = mouth.scaled(spans, [0.5] * 2400, 24000)
    quiet = mouth.scaled(spans, [0.01] * 2400, 24000)

    assert loud[0].weight == 0.8
    assert quiet[0].weight < 0.1


def test_weights_at_a_moment() -> None:
    track = [mouth.Span(0.0, 0.1, "aa", 0.8), mouth.Span(0.1, 0.2, "oh", 0.5)]

    assert mouth.weights_at(track, 0.15)["oh"] == 0.5
    assert mouth.weights_at(track, 0.3) == mouth.CLOSED


# ── sentences ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("buffer", "ready", "rest"),
    [
        ("Hi. How are", ["Hi."], "How are"),
        ("Dr. Who is here! And you? ", ["Dr. Who is here!", "And you?"], ""),
        ("", [], ""),
    ],
)
def test_split_ready(buffer: str, ready: list[str], rest: str) -> None:
    assert split_ready(buffer) == (ready, rest)


# ── microphone ────────────────────────────────────────────────────────────


def test_wav_header() -> None:
    data = wav(b"\x00\x01" * 10, 16000)

    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    assert struct.unpack("<I", data[24:28])[0] == 16000
    assert struct.unpack("<I", data[40:44])[0] == 20


def test_level_of_silence_and_noise() -> None:
    assert level(b"\x00\x00" * 100) == 0.0
    assert level(struct.pack("<2h", 16384, -16384)) == pytest.approx(0.5)


def test_silence_after_speech_ends() -> None:
    levels = [0.1] * 10 + [0.0] * 30

    assert silence_ended(levels, 0.05, 1.5, 0.02)


def test_silence_before_speech_does_not_end() -> None:
    assert not silence_ended([0.0] * 60, 0.05, 1.5, 0.02)


def test_short_pause_does_not_end() -> None:
    assert not silence_ended([0.1] * 10 + [0.0] * 10, 0.05, 1.5, 0.02)


# ── talk key ──────────────────────────────────────────────────────────────


def test_parse_ctrl_alt_space() -> None:
    assert parse("Ctrl+Alt+Space") == (0x0002 | 0x0001, 0x20)
    assert parse("Meta+F9") == (0x0008, 0x78)
    assert parse("Ctrl+Shift+K") == (0x0002 | 0x0004, ord("K"))


@pytest.mark.parametrize("sequence", ["Space", "Shift+A", "Ctrl+Alt+Volume"])
def test_parse_rejects(sequence: str) -> None:
    with pytest.raises(ValueError):
        parse(sequence)


class FakeUser32:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[tuple] = []

    def register(self, hwnd, id_, modifiers, key):
        self.calls.append(("register", hwnd, modifiers, key))
        return self.ok

    def unregister(self, hwnd, id_):
        self.calls.append(("unregister", hwnd))
        return True


def test_register_and_unregister(qapp) -> None:
    api = FakeUser32()
    keys = TalkHotkey(api)

    assert keys.register(42, "Ctrl+Alt+Space")
    keys.unregister()

    assert api.calls[0] == ("register", 42, 0x4000 | 0x0003, 0x20)
    assert api.calls[1] == ("unregister", 42)


def test_register_refused(qapp) -> None:
    assert not TalkHotkey(FakeUser32(ok=False)).register(42, "Ctrl+Alt+Space")


def test_wm_hotkey_emits_pressed(qapp) -> None:
    keys = TalkHotkey(FakeUser32())
    pressed: list[bool] = []
    keys.pressed.connect(lambda: pressed.append(True))
    msg = wintypes.MSG()
    msg.message = WM_HOTKEY
    msg.wParam = 0xC061

    # Qt hands over a shiboken pointer, which has a length of zero.
    handled, _ = _Filter(keys).nativeEventFilter(
        b"windows_generic_MSG", VoidPtr(ctypes.addressof(msg))
    )

    assert handled and pressed == [True]


# ── speech to text ────────────────────────────────────────────────────────


class Ready:
    def __init__(self) -> None:
        self.args: list[str] = []

    def launch(self, args):
        self.args = args

        class Process:
            def poll(self):
                return None

            def kill(self):
                pass

        return Process()


def test_command_line_flags(tmp_path) -> None:
    exe, model = tmp_path / "whisper-server.exe", tmp_path / "speech.bin"
    server = TranscriptionServer(exe, model)

    args = server.command(5000)

    assert args[:5] == [str(exe), "--host", "127.0.0.1", "--port", "5000"]
    assert "--language" in args and "en" in args


def test_missing_files(tmp_path) -> None:
    server = TranscriptionServer(tmp_path / "none.exe", tmp_path / "none.bin")

    with pytest.raises(SpeechUnavailable):
        server.url()


def _transcriber(tmp_path, handler) -> Transcriber:
    exe, model = tmp_path / "w.exe", tmp_path / "m.bin"
    exe.write_bytes(b"")
    model.write_bytes(b"")
    ready = Ready()
    server = TranscriptionServer(
        exe, model, launch=ready.launch, reachable=lambda p: True
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Transcriber(server, client)


def test_transcribe_returns_clean_text(tmp_path) -> None:
    transcriber = _transcriber(
        tmp_path,
        lambda request: httpx.Response(
            200, json={"text": " Hello there. [BLANK_AUDIO]"}
        ),
    )

    assert transcriber.transcribe(wav(b"")) == "Hello there."


def test_server_error_raises(tmp_path) -> None:
    transcriber = _transcriber(tmp_path, lambda request: httpx.Response(500))

    with pytest.raises(SpeechUnavailable):
        transcriber.transcribe(wav(b""))


def test_clean_drops_markers() -> None:
    assert clean("(music) [BLANK_AUDIO]") == ""


# ── voice ─────────────────────────────────────────────────────────────────


def test_pcm16_clips() -> None:
    assert struct.unpack("<3h", pcm16([0.0, 1.0, -2.0])) == (0, 32767, -32767)


class FakeVoice:
    def synthesize(self, text: str, voice: str, speed: float) -> Clip:
        return Clip([0.1] * 240, 24_000, ())


class FakeSink(QObject):
    """Plays at once: idle, with audio processed, as soon as it starts."""

    started: list[bytes] = []

    def __init__(self, audio) -> None:
        super().__init__()
        self._idle = False

    def start(self, device) -> None:
        FakeSink.started.append(bytes(device.readAll().data()))
        self._idle = True

    def stop(self) -> None:
        pass

    def state(self):
        return QtAudio.State.IdleState if self._idle else QtAudio.State.ActiveState

    def error(self):
        return QtAudio.Error.NoError

    def processedUSecs(self) -> int:
        return 10_000 if self._idle else 0


def test_speaker_says_every_sentence(qtbot) -> None:
    FakeSink.started = []
    speaker = Speaker(FakeVoice(), sink_factory=FakeSink)
    ended: list[bool] = []
    speaker.speaking.connect(ended.append)

    for text in ("One.", "Two.", "Three."):
        speaker.say(text, "af_heart", 1.0)

    qtbot.waitUntil(lambda: ended[-1:] == [False], timeout=3000)
    assert len(FakeSink.started) == 3
    speaker.close()


class FakeInput:
    def isNull(self) -> bool:
        return False


class FakeDevices:
    @staticmethod
    def defaultAudioInput() -> FakeInput:
        return FakeInput()


class FakeSource(QObject):
    """Hands over one second of loud audio at each read."""

    def __init__(self, device, audio, parent=None) -> None:
        super().__init__(parent)

    def start(self) -> "FakeSource":
        return self

    def readAll(self) -> QByteArray:
        return QByteArray(struct.pack("<h", 8000) * 16_000)

    def error(self):
        return QtAudio.Error.NoError

    def stop(self) -> None:
        pass


def test_microphone_stops_at_the_time_limit(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(microphone, "QMediaDevices", FakeDevices)
    monkeypatch.setattr(microphone, "QAudioSource", FakeSource)
    mic = microphone.Microphone(silence_s=1.5, max_s=2)
    heard: list[bytes] = []
    mic.finished.connect(heard.append)

    mic.start()
    qtbot.waitUntil(lambda: bool(heard), timeout=3000)

    assert not mic.isListening()
    # Two reads reach the limit; stopping keeps what the device still holds.
    assert heard == [heard[0]]
    assert len(heard[0]) == 44 + 3 * 32_000
