"""The microphone, open only while the user talks.

It records 16 kHz mono, which the speech engine reads, and keeps the audio in
memory. It stops when the user says so, after a short silence that follows
speech, or at a time limit, and hands over the audio as WAV bytes.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices, QtAudio

RATE = 16_000
_FRAME_S = 0.05
# A frame at this loudness or above counts as speech.
SPEECH_LEVEL = 0.02

NO_MICROPHONE = (
    "I can't find a microphone. Plug one in, or keep typing — that always works."
)
REFUSED = (
    "Windows did not let me use the microphone. Turn on Settings › Privacy & "
    "security › Microphone › Let desktop apps access your microphone, then try "
    "again."
)


def wav(pcm: bytes, rate: int = RATE) -> bytes:
    """16-bit mono PCM wrapped in a WAV header."""
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, 1, rate, rate * 2, 2, 16,
        b"data", len(pcm),
    )
    return header + pcm


def level(pcm: bytes) -> float:
    """The loudness of 16-bit PCM, from 0 to 1."""
    count = len(pcm) // 2
    if not count:
        return 0.0
    samples = struct.unpack(f"<{count}h", pcm[: count * 2])
    return (sum(s * s for s in samples) / count) ** 0.5 / 32768


def silence_ended(
    levels: Sequence[float], frame_s: float, silence_s: float, threshold: float
) -> bool:
    """Whether speech was heard and the last ``silence_s`` seconds were quiet."""
    if not any(value >= threshold for value in levels):
        return False
    quiet = round(silence_s / frame_s)
    tail = levels[-quiet:]
    return len(tail) >= quiet and all(value < threshold for value in tail)


class Microphone(QObject):
    #: The loudness of the last moment, from 0 to 1.
    level = Signal(float)
    #: The recording as WAV bytes.
    finished = Signal(bytes)
    #: Why it could not record.
    failed = Signal(str)

    def __init__(
        self, silence_s: float, max_s: float, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._silence_s = silence_s
        self._max_s = max_s
        self._source: QAudioSource | None = None
        self._device = None
        self._pcm = bytearray()
        self._levels: list[float] = []
        self._timer = QTimer(self)
        self._timer.setInterval(round(_FRAME_S * 1000))
        self._timer.timeout.connect(self._read)

    def isListening(self) -> bool:
        return self._source is not None

    def start(self) -> None:
        if self._source is not None:
            return
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self.failed.emit(NO_MICROPHONE)
            return
        audio = QAudioFormat()
        audio.setSampleRate(RATE)
        audio.setChannelCount(1)
        audio.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._pcm.clear()
        self._levels.clear()
        self._source = QAudioSource(device, audio, self)
        self._device = self._source.start()
        if self._source.error() != QtAudio.Error.NoError or self._device is None:
            self._discard()
            self.failed.emit(REFUSED)
            return
        self._timer.start()

    def stop(self) -> None:
        """Stop and hand over what was heard."""
        if self._source is None:
            return
        self._take()
        pcm = bytes(self._pcm)
        self._discard()
        self.finished.emit(wav(pcm))

    def cancel(self) -> None:
        """Stop and forget what was heard."""
        self._discard()

    def _take(self) -> None:
        """Keep what the device holds now."""
        if self._device is None:
            return
        chunk = bytes(self._device.readAll().data())
        if chunk:
            self._pcm.extend(chunk)
            loudness = level(chunk)
            self._levels.append(loudness)
            self.level.emit(min(1.0, loudness * 8))

    def _read(self) -> None:
        if self._source is None:
            return
        self._take()
        if self._source.error() != QtAudio.Error.NoError:
            self._discard()
            self.failed.emit(REFUSED)
            return
        heard_s = len(self._pcm) / (RATE * 2)
        ended = silence_ended(self._levels, _FRAME_S, self._silence_s, SPEECH_LEVEL)
        if ended or heard_s >= self._max_s:
            self.stop()

    def _discard(self) -> None:
        self._timer.stop()
        if self._source is not None:
            self._source.stop()
            self._source.deleteLater()
        self._source = None
        self._device = None
        self._pcm.clear()
