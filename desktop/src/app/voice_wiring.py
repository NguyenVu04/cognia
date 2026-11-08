"""Talking and listening: the talk key, the microphone buttons, speech into
the composer, and replies said aloud with the mouth in time."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from src.app import config
from src.infrastructure.voice.hotkey import TalkHotkey
from src.infrastructure.voice.microphone import Microphone
from src.infrastructure.voice.sentences import split_ready
from src.infrastructure.voice.speaker import KokoroVoice, Speaker

if TYPE_CHECKING:
    from src.app.application import Cognia

NOT_CAUGHT = "I didn't catch that. Try again, a little closer to the microphone."
KEY_TAKEN = (
    "Another app already uses {key}, so the talk key is off. Choose another in "
    "Settings › Voice."
)


class VoiceWiring(QObject):
    #: WAV bytes for the model thread to turn into words.
    askTranscribe = Signal(bytes)

    def __init__(self, cognia: Cognia) -> None:
        super().__init__()
        self.c = cognia
        self.speak_aloud = True
        self.hotkey = ""
        self._voice = "af_heart"
        self._speed = 1.0
        self._buffer = ""
        self._failed_once = False
        self.mic = Microphone(
            config.TALK_SILENCE_SECONDS, config.TALK_MAX_SECONDS, self
        )
        self.keys = TalkHotkey(parent=self)
        self.speaker = Speaker(
            KokoroVoice(
                config.model_path(config.VOICE_MODEL), config.model_path(config.VOICES)
            ),
            parent=self,
        )
        chat, companion, worker = cognia.window.chat, cognia.companion, cognia.worker

        cognia.app.installNativeEventFilter(self.keys.filter)
        self.keys.pressed.connect(self._key_pressed)
        chat.micToggled.connect(self.toggle_listening)
        chat.typingStarted.connect(self.speaker.stop)
        chat.stopSpeakingRequested.connect(self.speaker.stop)
        companion.talkPressed.connect(self._hold_started)
        companion.talkReleased.connect(self.mic.stop)
        self.mic.level.connect(chat.setLevel)
        self.mic.finished.connect(self._heard)
        self.mic.failed.connect(self._mic_failed)
        self.askTranscribe.connect(worker.transcribe)
        worker.transcribed.connect(self._transcribed)
        worker.transcribeFailed.connect(self._notice)
        worker.chunk.connect(self._chunk)
        cognia.bridge.replyFinished.connect(self._reply_finished)
        cognia.bridge.voiceChanged.connect(self._voice_changed)
        self.speaker.speaking.connect(chat.setSpeaking)
        self.speaker.mouth.connect(companion.setMouth)
        self.speaker.failed.connect(self._speaker_failed)

    # ── settings ──────────────────────────────────────────────────────────

    def set_settings(self, speak_aloud: bool, hotkey: str) -> None:
        self.speak_aloud = speak_aloud
        if not speak_aloud:
            self.speaker.stop()
        if hotkey != self.hotkey:
            self.hotkey = hotkey
            hwnd = int(self.c.window.winId())
            if not self.keys.register(hwnd, hotkey):
                self._notice(KEY_TAKEN.format(key=hotkey))
            self.c.window.chat.setTalkHint(hotkey)
            self.c.window.tips_step.setHotkey(hotkey)

    @Slot(str, float)
    def _voice_changed(self, voice: str, speed: float) -> None:
        self._voice, self._speed = voice, speed

    # ── listening ─────────────────────────────────────────────────────────

    def _key_pressed(self) -> None:
        self.c.show_window()
        self.toggle_listening()

    def toggle_listening(self) -> None:
        if self.mic.isListening():
            self.mic.stop()
            return
        self.speaker.stop()
        self.c.window.chat.setListening(True)
        self.mic.start()

    def _hold_started(self) -> None:
        if not self.mic.isListening():
            self.toggle_listening()

    @Slot(bytes)
    def _heard(self, wav: bytes) -> None:
        self.c.window.chat.setListening(False)
        self.askTranscribe.emit(wav)

    @Slot(str)
    def _transcribed(self, text: str) -> None:
        if not text:
            self._notice(NOT_CAUGHT)
            return
        self.c.window.chat.setTranscript(text)

    @Slot(str)
    def _mic_failed(self, text: str) -> None:
        self.c.window.chat.setListening(False)
        self._notice(text)

    # ── speaking ──────────────────────────────────────────────────────────

    @Slot(str)
    def _chunk(self, text: str) -> None:
        if not self.speak_aloud:
            return
        self._buffer += text
        sentences, self._buffer = split_ready(self._buffer)
        for sentence in sentences:
            self.speaker.say(sentence, self._voice, self._speed)

    @Slot(str, str, str, str)
    def _reply_finished(
        self, text: str, note: str, check: str, message_id: str
    ) -> None:
        rest, self._buffer = self._buffer.strip(), ""
        if self.speak_aloud and rest:
            self.speaker.say(rest, self._voice, self._speed)

    def say_text(self, text: str) -> None:
        """Say a whole message aloud, such as a greeting."""
        if not self.speak_aloud:
            return
        sentences, rest = split_ready(text + " ")
        for sentence in [*sentences, rest.strip()]:
            self.speaker.say(sentence, self._voice, self._speed)

    @Slot(str)
    def _speaker_failed(self, text: str) -> None:
        # Said once a run: the replies stay written either way.
        if not self._failed_once:
            self._failed_once = True
            self._notice(text)

    def _notice(self, text: str) -> None:
        self.c.window.chat.showNotice(text)

    def close(self) -> None:
        self.mic.cancel()
        self.keys.unregister()
        self.speaker.close()
