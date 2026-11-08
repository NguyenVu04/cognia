"""Speech to text: a whisper.cpp server on this machine.

The server starts at the first use, listens on 127.0.0.1 only, and ends with
Cognia. The audio goes to it in memory and is never written to a file.
"""

from __future__ import annotations

import socket
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from src.infrastructure.ai.job_object import JobObject

_HOST = "127.0.0.1"
NOT_STARTED = (
    "I can't hear right now: the speech engine did not start. Typing still works."
)
NOT_HEARD = "I can't hear right now: the speech engine stopped. Typing still works."
MISSING = (
    "I can't hear right now: a speech file is missing. Reinstalling Cognia "
    "puts it back. Typing still works."
)


class SpeechUnavailable(Exception):
    """Speech could not be turned into text, with a sentence saying so."""


class TranscriptionServer:
    """Starts ``whisper-server`` when first asked for its address."""

    def __init__(
        self,
        exe: Path,
        model: Path,
        *,
        threads: int = 4,
        start_seconds: float = 30,
        launch: Callable[[list[str]], subprocess.Popen] | None = None,
        reachable: Callable[[int], bool] | None = None,
    ) -> None:
        self._exe = exe
        self._model = model
        self._threads = threads
        self._start_seconds = start_seconds
        self._launch = launch or self._start_process
        self._reachable = reachable or _accepts
        self._process: subprocess.Popen | None = None
        self._port = 0
        self._job: JobObject | None = None
        self._lock = threading.Lock()

    def command(self, port: int) -> list[str]:
        return [
            str(self._exe),
            "--host",
            _HOST,
            "--port",
            str(port),
            "--model",
            str(self._model),
            "--language",
            "en",
            "--threads",
            str(self._threads),
            "--no-timestamps",
        ]

    def url(self) -> str:
        """The inference address. Starts the server if needed; raises
        :class:`SpeechUnavailable` if it cannot."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return f"http://{_HOST}:{self._port}/inference"
            if not self._exe.is_file() or not self._model.is_file():
                raise SpeechUnavailable(MISSING)
            self._port = _free_port()
            try:
                self._process = self._launch(self.command(self._port))
            except OSError as error:
                raise SpeechUnavailable(NOT_STARTED) from error
            deadline = time.monotonic() + self._start_seconds
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    break
                if self._reachable(self._port):
                    return f"http://{_HOST}:{self._port}/inference"
                time.sleep(0.2)
            self.stop()
            raise SpeechUnavailable(NOT_STARTED)

    def stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.kill()
        self._process = None
        if self._job is not None:
            self._job.close()
            self._job = None

    def _start_process(self, args: list[str]) -> subprocess.Popen:
        # The server log goes nowhere, because it can hold the user's words.
        process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            if self._job is None:
                self._job = JobObject()
            self._job.assign(process.pid)
        except OSError:
            process.kill()
            raise
        return process


class Transcriber:
    """Turns WAV audio into English text."""

    def __init__(
        self, server: TranscriptionServer, client: httpx.Client | None = None
    ) -> None:
        self._server = server
        self._http = client or httpx.Client(timeout=httpx.Timeout(60, connect=3))

    def transcribe(self, wav: bytes) -> str:
        """The words, or "" if nothing was recognised. Raises
        :class:`SpeechUnavailable`."""
        url = self._server.url()
        try:
            response = self._http.post(
                url,
                files={"file": ("speech.wav", wav, "audio/wav")},
                data={"response_format": "json", "temperature": "0"},
            )
        except httpx.HTTPError as error:
            raise SpeechUnavailable(NOT_HEARD) from error
        if response.status_code != 200:
            raise SpeechUnavailable(NOT_HEARD)
        try:
            text = str(response.json().get("text", ""))
        except ValueError as error:
            raise SpeechUnavailable(NOT_HEARD) from error
        return clean(text)

    def close(self) -> None:
        self._http.close()
        self._server.stop()


def clean(text: str) -> str:
    """The words without the markers whisper writes for silence or noise,
    such as ``[BLANK_AUDIO]`` or ``(music)``."""
    words = []
    for word in text.split():
        if word.startswith(("[", "(")) or word.endswith(("]", ")")):
            continue
        words.append(word)
    return " ".join(words).strip()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind((_HOST, 0))
        return probe.getsockname()[1]


def _accepts(port: int) -> bool:
    try:
        with socket.create_connection((_HOST, port), timeout=0.5):
            return True
    except OSError:
        return False
