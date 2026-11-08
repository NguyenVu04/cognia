"""Starts the two llama-server processes and keeps them alive.

The chat server runs on the GPU that measured fastest, among the GPUs with
enough dedicated memory for the model. The measurement runs once, and the
caller keeps the GPU's name. If no GPU can run it, the CPU build runs it for the
rest of the run. The embedding model is small, so it always runs on the CPU and
leaves the GPU memory to the chat model.

A server starts at the first call that needs it. A server that ended is started
again at the next call, up to a limit for the run. Each start has a new port
and a new key. Every call happens on the model thread, except :meth:`stop`.
"""

from __future__ import annotations

import re
import secrets
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import httpx

from src.infrastructure.ai.gpu_memory import dedicated_memory, name_key
from src.infrastructure.ai.job_object import JobObject

CHAT = "chat"
EMBEDDING = "embedding"

MISSING = (
    "A file that Cognia needs for its model is missing. Reinstalling Cognia "
    "repairs this."
)
NOT_STARTED = (
    "The model on this machine could not start. Restarting Cognia may help; if "
    "it does not, this machine may be below what Cognia needs."
)

_HOST = "127.0.0.1"
_POLL_SECONDS = 0.25
_STOP_SECONDS = 5
# About 400 tokens: a first reply reads a prompt of that size, so the fastest
# GPU here is the one that answers first.
_BENCH_PROMPT = " ".join(
    ["The quiet river bends past the old mill, and the light falls on the water."]
    * 28
)
_BENCH_TOKENS = 32
_DEVICE_LINE = re.compile(r"^\s*(\S+):\s*(.+?)\s*\(\d+ MiB, \d+ MiB free\)\s*$")
# Beyond the model file, the context and the work buffers need GPU memory too:
# 263 MiB measured with an 8192-token context, doubled for headroom. A larger
# context needs more.
_VRAM_MARGIN = 512 * 1024 * 1024


class ServerState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    FALLBACK_CPU = "fallback_cpu"
    RESTARTING = "restarting"
    FAILED = "failed"


class ModelUnavailable(Exception):
    """No server can answer, with a sentence for the user."""


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    api_key: str


@dataclass(frozen=True)
class Device:
    """A GPU that the Vulkan build can use. ``dedicated`` is its own memory in
    bytes, or ``None`` if Windows did not report it."""

    id: str
    name: str
    dedicated: int | None = None


@dataclass(frozen=True)
class _Running:
    process: object
    endpoint: Endpoint
    exe: Path
    device: tuple[str, ...]


@dataclass
class _Server:
    model: Path
    state: ServerState = ServerState.STOPPED
    running: _Running | None = None
    restarts: int = 0
    flags: tuple[str, ...] = field(default_factory=tuple)


class ModelSupervisor:
    """The chat server and the embedding server.

    ``chat_device`` is the name of the GPU chosen in an earlier run, or
    ``None``. ``on_device_chosen`` receives the name of a newly chosen GPU, on
    the model thread. ``platform`` does the processes, HTTP and time, and a test
    replaces it.
    """

    def __init__(
        self,
        vulkan: Path,
        cpu: Path,
        chat_model: Path,
        embedding_model: Path,
        *,
        context: int,
        cache_ram_mib: int,
        idle_seconds: int | None,
        start_seconds: float,
        restarts: int,
        chat_device: str | None,
        on_device_chosen: Callable[[str], None],
        platform: LocalPlatform | None = None,
    ) -> None:
        self._vulkan = vulkan
        self._cpu = cpu
        self._start_seconds = start_seconds
        self._restarts = restarts
        self._chat_device = chat_device
        self._on_device_chosen = on_device_chosen
        self._platform = platform or LocalPlatform()
        idle = ()
        if idle_seconds is not None:
            idle = ("--sleep-idle-seconds", str(idle_seconds))
        self._servers = {
            CHAT: _Server(
                chat_model,
                flags=("-c", str(context), "--cache-ram", str(cache_ram_mib), *idle),
            ),
            EMBEDDING: _Server(embedding_model, flags=("--embedding", *idle)),
        }

    def state(self, server: str) -> ServerState:
        return self._servers[server].state

    def retry(self) -> None:
        """Let a server that failed to start be started again at the next
        request."""
        for slot in self._servers.values():
            if slot.state is ServerState.FAILED:
                slot.state = ServerState.STOPPED
                slot.restarts = 0

    def remember_device(self, name: str | None) -> None:
        """The GPU chosen in an earlier run, read after this object exists.
        Call it before the first request for the chat server."""
        self._chat_device = name

    def endpoint(self, server: str) -> Endpoint:
        """Where ``server`` answers, after it is healthy. Blocks while it starts.
        Raises :class:`ModelUnavailable`."""
        slot = self._servers[server]
        if slot.state is ServerState.FAILED:
            raise ModelUnavailable(NOT_STARTED)
        if slot.running is not None:
            if slot.running.process.poll() is None:
                return slot.running.endpoint
            return self._restart(slot)
        self._check_files(slot)
        slot.state = ServerState.STARTING
        if server == CHAT:
            running = self._start_chat(slot)
        else:
            running = self._launch(self._cpu, slot)
        if running is None:
            slot.state = ServerState.FAILED
            raise ModelUnavailable(NOT_STARTED)
        slot.running = running
        slot.state = ServerState.READY
        return running.endpoint

    def stop(self) -> None:
        """End both servers. Call it after the model thread has stopped."""
        for slot in self._servers.values():
            if slot.running is not None:
                self._end(slot.running.process)
                slot.running = None
            slot.state = ServerState.STOPPED
        self._platform.close()

    # ── starting ──────────────────────────────────────────────────────────

    def _check_files(self, slot: _Server) -> None:
        needed = [self._cpu, slot.model]
        if slot is self._servers[CHAT]:
            needed.append(self._vulkan)
        if not all(path.is_file() for path in needed):
            raise ModelUnavailable(MISSING)

    def _start_chat(self, slot: _Server) -> _Running | None:
        # A GPU built into the processor reports shared memory, so only its
        # dedicated memory tells whether the model fits.
        needed = slot.model.stat().st_size + _VRAM_MARGIN
        devices = [
            d
            for d in self._platform.devices(self._vulkan)
            if d.dedicated is None or d.dedicated >= needed
        ]
        stored = next((d for d in devices if d.name == self._chat_device), None)
        if stored is not None:
            running = self._launch(self._vulkan, slot, ("--device", stored.id))
            if running is not None:
                return running
        candidates = [d for d in devices if d is not stored]
        chosen = self._measure(slot, candidates)
        if chosen is not None:
            device, running = chosen
            if device.name != self._chat_device:
                self._chat_device = device.name
                self._on_device_chosen(device.name)
            return running
        slot.state = ServerState.FALLBACK_CPU
        return self._launch(self._cpu, slot)

    def _measure(
        self, slot: _Server, devices: list[Device]
    ) -> tuple[Device, _Running] | None:
        """Start the chat model on each GPU, and keep the one that answers a
        fixed prompt fastest. A GPU that does not start is skipped."""
        best: tuple[Device, _Running] | None = None
        best_seconds = float("inf")
        for device in devices:
            running = self._launch(self._vulkan, slot, ("--device", device.id))
            if running is None:
                continue
            if len(devices) == 1:
                return device, running
            seconds = self._platform.benchmark(running.endpoint)
            if seconds is not None and seconds < best_seconds:
                if best is not None:
                    self._end(best[1].process)
                best, best_seconds = (device, running), seconds
            else:
                self._end(running.process)
        return best

    def _launch(
        self, exe: Path, slot: _Server, device: tuple[str, ...] = ()
    ) -> _Running | None:
        """A healthy server, or ``None`` if it did not become healthy in time."""
        port = self._platform.free_port()
        key = self._platform.new_key()
        # The server fits the layers to the GPU's free memory.
        layers = ("-ngl", "auto") if exe == self._vulkan else ()
        flags = (*device, *layers, *slot.flags)
        args = [
            str(exe), "-m", str(slot.model), "--host", _HOST, "--port", str(port),
            "--api-key", key, "--no-webui", "--offline", "-np", "1", *flags,
        ]
        try:
            process = self._platform.start(args)
        except OSError:
            return None
        deadline = self._platform.now() + self._start_seconds
        while self._platform.now() < deadline:
            if process.poll() is not None:
                return None
            if self._platform.healthy(port):
                return _Running(process, Endpoint(f"http://{_HOST}:{port}", key),
                                exe, device)
            self._platform.sleep(_POLL_SECONDS)
        self._end(process)
        return None

    def _restart(self, slot: _Server) -> Endpoint:
        last = slot.running
        while slot.restarts < self._restarts:
            slot.restarts += 1
            slot.state = ServerState.RESTARTING
            running = self._launch(last.exe, slot, last.device)
            if running is not None:
                slot.running = running
                slot.state = ServerState.READY
                return running.endpoint
        slot.running = None
        slot.state = ServerState.FAILED
        raise ModelUnavailable(NOT_STARTED)

    def _end(self, process) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(_STOP_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()


class LocalPlatform:
    """The real processes, HTTP calls and clock."""

    def __init__(self) -> None:
        self._job: JobObject | None = None
        self._http = httpx.Client(timeout=httpx.Timeout(120, connect=2))

    def start(self, args: list[str]) -> subprocess.Popen:
        """Start ``args`` with no window. The server log goes nowhere, because
        it can hold the user's words."""
        process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            if self._job is None:
                self._job = JobObject()
            self._job.assign(process.pid)
        except OSError:
            process.kill()
            raise
        return process

    def healthy(self, port: int) -> bool:
        try:
            response = self._http.get(f"http://{_HOST}:{port}/health", timeout=2)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def devices(self, exe: Path) -> list[Device]:
        """The GPUs that the Vulkan build can use, each with its dedicated
        memory where Windows reports it. Empty if they cannot be listed."""
        try:
            result = subprocess.run(
                [str(exe), "--list-devices"],
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        return with_memory(
            parse_devices(result.stdout + result.stderr), dedicated_memory()
        )

    def benchmark(self, endpoint: Endpoint) -> float | None:
        """Seconds to read the fixed prompt and write a short answer, or
        ``None`` if the server did not answer.

        A short request runs first and is not timed: the first request on a
        GPU also pays for waking it and preparing its work, once.
        """
        if self._ask(endpoint, "Hello.", 1) is None:
            return None
        return self._ask(endpoint, _BENCH_PROMPT, _BENCH_TOKENS)

    def _ask(self, endpoint: Endpoint, text: str, tokens: int) -> float | None:
        body = {
            "messages": [{"role": "user", "content": text}],
            "max_tokens": tokens,
            "stream": False,
        }
        started = time.monotonic()
        try:
            response = self._http.post(
                f"{endpoint.base_url}/v1/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {endpoint.api_key}"},
            )
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        return time.monotonic() - started

    def free_port(self) -> int:
        with socket.socket() as probe:
            probe.bind((_HOST, 0))
            return probe.getsockname()[1]

    def new_key(self) -> str:
        return secrets.token_urlsafe(24)

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def close(self) -> None:
        """End anything the job still holds."""
        if self._job is not None:
            self._job.close()
            self._job = None
        self._http.close()


def parse_devices(text: str) -> list[Device]:
    """The devices in the output of ``llama-server --list-devices``."""
    devices = []
    for line in text.splitlines():
        match = _DEVICE_LINE.match(line)
        if match:
            devices.append(Device(match.group(1), match.group(2)))
    return devices


def with_memory(devices: list[Device], memory: dict[str, int]) -> list[Device]:
    """Each device with its dedicated memory, matched by name. A device with no
    match keeps ``None``, so it is measured rather than refused."""
    return [
        Device(d.id, d.name, memory.get(name_key(d.name))) for d in devices
    ]
