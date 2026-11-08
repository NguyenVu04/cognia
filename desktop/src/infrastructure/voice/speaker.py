"""Saying replies aloud in the character's voice, with the mouth in time.

Kokoro makes the audio of each sentence on its own thread, so playing one
sentence never waits for the next to be made. Qt plays the audio. While it
plays, the speaker sends the mouth weights for the moment of the audio, from
the phoneme times that Kokoro reports. The audio stays in memory.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink

from src.infrastructure.voice import mouth

NOT_SPOKEN = (
    "I can't speak right now: the voice engine did not start. My replies stay written."
)
MISSING = (
    "I can't speak right now: a voice file is missing. Reinstalling Cognia puts it "
    "back. My replies stay written."
)
_FRAME_MS = 33


@dataclass(frozen=True)
class Clip:
    """One sentence as audio: samples from -1 to 1, the rate, and the mouth."""

    samples: Sequence[float]
    rate: int
    track: tuple[mouth.Span, ...]


class KokoroVoice:
    """Kokoro-82M through ``kokoro-onnx``, loaded at the first sentence. Its
    phonemes come from the espeak-ng that ``espeakng-loader`` ships."""

    def __init__(self, model: Path, voices: Path) -> None:
        self._model = model
        self._voices = voices
        self._engine = None

    def synthesize(self, text: str, voice: str, speed: float) -> Clip:
        if self._engine is None:
            if not self._model.is_file() or not self._voices.is_file():
                raise FileNotFoundError(self._model)
            from kokoro_onnx import Kokoro

            self._engine = Kokoro(str(self._model), str(self._voices))
        samples, rate, timings = self._engine.create_timed(text, voice, speed)
        triples = [(t.phoneme, float(t.start), float(t.end)) for t in timings]
        flat = samples.tolist()
        return Clip(flat, rate, tuple(mouth.scaled(mouth.spans(triples), flat, rate)))


def pcm16(samples: Sequence[float]) -> bytes:
    """Samples from -1 to 1 as 16-bit little-endian PCM."""
    import array

    out = array.array("h", (int(max(-1.0, min(1.0, s)) * 32767) for s in samples))
    return out.tobytes()


class Speaker(QObject):
    """Lives on the GUI thread. ``say`` queues a sentence; ``stop`` ends all
    speech at once."""

    #: The weight of each mouth shape for this moment.
    mouth = Signal(object)
    speaking = Signal(bool)
    failed = Signal(str)
    _made = Signal(int, object)
    _not_made = Signal(int, str)

    def __init__(
        self,
        engine: KokoroVoice,
        *,
        sink_factory: Callable[[QAudioFormat], QAudioSink] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._sink_factory = sink_factory or QAudioSink
        self._jobs: queue.Queue = queue.Queue()
        self._generation = 0
        self._clips: list[Clip] = []
        self._pending = 0
        self._sink: QAudioSink | None = None
        self._buffer: QBuffer | None = None
        self._track: tuple[mouth.Span, ...] = ()
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._move_mouth)
        self._made.connect(self._on_made)
        self._not_made.connect(self._on_not_made)
        self._worker = threading.Thread(
            target=self._work, name="cognia-speech", daemon=True
        )
        self._worker.start()

    def say(self, text: str, voice: str, speed: float) -> None:
        if not text.strip():
            return
        self._pending += 1
        self._jobs.put((self._generation, text, voice, speed))
        self.speaking.emit(True)

    def stop(self) -> None:
        """Stop at once. Sentences not said yet are dropped."""
        self._generation += 1
        self._pending = 0
        self._clips.clear()
        self._end_clip()
        self.mouth.emit(dict(mouth.CLOSED))
        self.speaking.emit(False)

    def isSpeaking(self) -> bool:
        return self._sink is not None or self._pending > 0 or bool(self._clips)

    def close(self) -> None:
        self.stop()
        self._jobs.put(None)

    # ── the worker thread ─────────────────────────────────────────────────

    def _work(self) -> None:
        while (job := self._jobs.get()) is not None:
            generation, text, voice, speed = job
            if generation != self._generation:
                continue
            try:
                clip = self._engine.synthesize(text, voice, speed)
            except FileNotFoundError:
                self._not_made.emit(generation, MISSING)
                continue
            except Exception:  # noqa: BLE001 - the reply stays written
                self._not_made.emit(generation, NOT_SPOKEN)
                continue
            self._made.emit(generation, clip)

    # ── playing, on the GUI thread ────────────────────────────────────────

    def _on_made(self, generation: int, clip: Clip) -> None:
        if generation != self._generation:
            return
        self._pending = max(0, self._pending - 1)
        self._clips.append(clip)
        if self._sink is None:
            self._play_next()

    def _on_not_made(self, generation: int, text: str) -> None:
        if generation != self._generation:
            return
        self.stop()
        self.failed.emit(text)

    def _play_next(self) -> None:
        if not self._clips:
            if self._pending == 0:
                self.mouth.emit(dict(mouth.CLOSED))
                self.speaking.emit(False)
            return
        clip = self._clips.pop(0)
        audio = QAudioFormat()
        audio.setSampleRate(clip.rate)
        audio.setChannelCount(1)
        audio.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._buffer = QBuffer(self)
        self._buffer.setData(QByteArray(pcm16(clip.samples)))
        self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._track = clip.track
        self._sink = self._sink_factory(audio)
        self._sink.stateChanged.connect(self._state_changed)
        self._sink.start(self._buffer)
        self._timer.start()

    def _state_changed(self, state) -> None:
        if state == QAudio.State.IdleState:
            self._end_clip()
            self._play_next()
        elif state == QAudio.State.StoppedState and self._sink is not None:
            if self._sink.error() != QAudio.Error.NoError:
                self.stop()
                self.failed.emit(NOT_SPOKEN)

    def _move_mouth(self) -> None:
        if self._sink is None:
            return
        seconds = self._sink.processedUSecs() / 1_000_000
        self.mouth.emit(mouth.weights_at(self._track, seconds))

    def _end_clip(self) -> None:
        self._timer.stop()
        sink, self._sink = self._sink, None
        if sink is not None:
            sink.stateChanged.disconnect(self._state_changed)
            sink.stop()
            sink.deleteLater()
        if self._buffer is not None:
            self._buffer.close()
            self._buffer.deleteLater()
            self._buffer = None
