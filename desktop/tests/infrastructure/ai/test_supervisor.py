from pathlib import Path

import pytest

from src.infrastructure.ai.gpu_memory import dedicated_memory
from src.infrastructure.ai.supervisor import (
    CHAT,
    EMBEDDING,
    MISSING,
    NOT_STARTED,
    Device,
    ModelSupervisor,
    ModelUnavailable,
    ServerState,
    parse_devices,
    with_memory,
)

MIB = 1024 * 1024
INTEL = Device("Vulkan0", "Intel(R) Iris(R) Xe Graphics")
NVIDIA = Device("Vulkan1", "NVIDIA GeForce RTX 3050 Ti Laptop GPU")
# The dedicated memory that Windows reports on the author's laptop.
INTEL_SMALL = Device(INTEL.id, INTEL.name, 128 * MIB)
NVIDIA_4GB = Device(NVIDIA.id, NVIDIA.name, 3962 * MIB)


class FakeProcess:
    def __init__(self, args: list[str], dies: bool) -> None:
        self.args = args
        self.code = 1 if dies else None
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self) -> None:
        self.terminated = True
        self.code = 0

    def wait(self, timeout=None) -> int:
        return self.code

    def kill(self) -> None:
        self.code = -9

    @property
    def device(self) -> str:
        if "--device" in self.args:
            return self.args[self.args.index("--device") + 1]
        return "cpu" if "cpu" in self.args[0] else "vulkan"


class FakePlatform:
    """Each process starts healthy unless its device is in ``dies`` (it ends at
    once) or ``hangs`` (it never answers /health)."""

    def __init__(self, devices=(INTEL, NVIDIA), times=None) -> None:
        self.device_list = list(devices)
        self.times = times or {"Vulkan0": 7.0, "Vulkan1": 1.3}
        self.dies: set[str] = set()
        self.hangs: set[str] = set()
        self.started: list[FakeProcess] = []
        self.benchmarked: list[str] = []
        self.clock = 0.0
        self.port = 9000
        self.keys = 0
        self.closed = False

    def start(self, args):
        process = FakeProcess(args, dies=False)
        process.code = 1 if process.device in self.dies else None
        self.started.append(process)
        return process

    def healthy(self, port: int) -> bool:
        process = self.started[-1]
        return process.device not in self.hangs

    def devices(self, exe):
        return list(self.device_list)

    def benchmark(self, endpoint):
        device = self.started[-1].device
        self.benchmarked.append(device)
        return self.times.get(device)

    def free_port(self) -> int:
        self.port += 1
        return self.port

    def new_key(self) -> str:
        self.keys += 1
        return f"key-{self.keys}"

    def now(self) -> float:
        return self.clock

    def sleep(self, seconds: float) -> None:
        self.clock += seconds

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def files(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "vulkan": tmp_path / "runtime" / "vulkan" / "llama-server.exe",
        "cpu": tmp_path / "runtime" / "cpu" / "llama-server.exe",
        "chat": tmp_path / "chat.gguf",
        "embedding": tmp_path / "embedding.gguf",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    return paths


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform()


def make(files, platform, *, device=None, idle=None, chosen=None) -> ModelSupervisor:
    return ModelSupervisor(
        files["vulkan"], files["cpu"], files["chat"], files["embedding"],
        context=8192, idle_seconds=idle, start_seconds=10, restarts=3,
        chat_device=device,
        on_device_chosen=(chosen.append if chosen is not None else lambda name: None),
        platform=platform,
    )


def test_chat_args_exact(files, platform) -> None:
    platform.device_list = [NVIDIA]
    supervisor = make(files, platform)

    endpoint = supervisor.endpoint(CHAT)

    assert platform.started[0].args == [
        str(files["vulkan"]), "-m", str(files["chat"]), "--host", "127.0.0.1",
        "--port", "9001", "--api-key", "key-1", "--no-webui", "--offline",
        "-np", "1", "--device", "Vulkan1", "-c", "8192",
    ]
    assert (endpoint.base_url, endpoint.api_key) == ("http://127.0.0.1:9001", "key-1")
    assert supervisor.state(CHAT) is ServerState.READY


def test_embedding_runs_on_cpu(files, platform) -> None:
    make(files, platform).endpoint(EMBEDDING)

    args = platform.started[0].args
    assert args[0] == str(files["cpu"])
    assert args[2] == str(files["embedding"])
    assert args[-1] == "--embedding"
    assert "--device" not in args


def test_idle_flag_present(files, platform) -> None:
    make(files, platform, idle=600).endpoint(EMBEDDING)

    assert platform.started[0].args[-2:] == ["--sleep-idle-seconds", "600"]


def test_idle_flag_absent(files, platform) -> None:
    make(files, platform).endpoint(EMBEDDING)

    assert "--sleep-idle-seconds" not in platform.started[0].args


def test_second_call_does_not_start_again(files, platform) -> None:
    supervisor = make(files, platform)
    first = supervisor.endpoint(EMBEDDING)

    assert supervisor.endpoint(EMBEDDING) == first
    assert len(platform.started) == 1


def test_measures_every_gpu_and_keeps_fastest(files, platform) -> None:
    chosen: list[str] = []
    supervisor = make(files, platform, chosen=chosen)

    endpoint = supervisor.endpoint(CHAT)

    intel, nvidia = platform.started
    assert platform.benchmarked == ["Vulkan0", "Vulkan1"]
    assert intel.terminated and not nvidia.terminated
    assert endpoint.api_key == "key-2"
    assert chosen == [NVIDIA.name]


def test_slower_later_gpu_is_ended(files, platform) -> None:
    platform.times = {"Vulkan0": 1.0, "Vulkan1": 2.0}
    chosen: list[str] = []

    make(files, platform, chosen=chosen).endpoint(CHAT)

    intel, nvidia = platform.started
    assert nvidia.terminated and not intel.terminated
    assert chosen == [INTEL.name]


def test_stored_device_is_used_without_measuring(files, platform) -> None:
    chosen: list[str] = []
    make(files, platform, device=NVIDIA.name, chosen=chosen).endpoint(CHAT)

    assert [p.device for p in platform.started] == ["Vulkan1"]
    assert platform.benchmarked == []
    assert chosen == []


def test_stored_device_gone_measures_again(files, platform) -> None:
    chosen: list[str] = []
    make(files, platform, device="Old GPU", chosen=chosen).endpoint(CHAT)

    assert platform.benchmarked == ["Vulkan0", "Vulkan1"]
    assert chosen == [NVIDIA.name]


def test_stored_device_fails_measures_the_others(files, platform) -> None:
    platform.dies = {"Vulkan1"}
    chosen: list[str] = []

    make(files, platform, device=NVIDIA.name, chosen=chosen).endpoint(CHAT)

    assert [p.device for p in platform.started] == ["Vulkan1", "Vulkan0"]
    assert chosen == [INTEL.name]


def test_single_gpu_needs_no_benchmark(files, platform) -> None:
    platform.device_list = [INTEL]
    chosen: list[str] = []

    make(files, platform, chosen=chosen).endpoint(CHAT)

    assert platform.benchmarked == []
    assert chosen == [INTEL.name]


def test_every_gpu_exits_falls_back_to_cpu(files, platform) -> None:
    platform.dies = {"Vulkan0", "Vulkan1"}
    chosen: list[str] = []
    supervisor = make(files, platform, chosen=chosen)

    supervisor.endpoint(CHAT)

    assert platform.started[-1].device == "cpu"
    assert supervisor.state(CHAT) is ServerState.READY
    assert chosen == []


def test_gpu_that_never_answers_times_out(files, platform) -> None:
    platform.device_list = [NVIDIA]
    platform.hangs = {"Vulkan1"}
    supervisor = make(files, platform)

    supervisor.endpoint(CHAT)

    hung, cpu = platform.started
    assert hung.terminated
    assert cpu.device == "cpu"


def test_no_gpu_runs_on_cpu(files, platform) -> None:
    platform.device_list = []

    make(files, platform).endpoint(CHAT)

    assert [p.device for p in platform.started] == ["cpu"]


def test_cpu_fails_too(files, platform) -> None:
    platform.dies = {"Vulkan0", "Vulkan1", "cpu"}
    supervisor = make(files, platform)

    with pytest.raises(ModelUnavailable, match=NOT_STARTED):
        supervisor.endpoint(CHAT)
    started = len(platform.started)
    with pytest.raises(ModelUnavailable):
        supervisor.endpoint(CHAT)

    assert supervisor.state(CHAT) is ServerState.FAILED
    assert len(platform.started) == started


def test_ended_server_restarts_with_new_key(files, platform) -> None:
    supervisor = make(files, platform)
    first = supervisor.endpoint(EMBEDDING)
    platform.started[-1].code = 1

    second = supervisor.endpoint(EMBEDDING)

    assert second.api_key != first.api_key
    assert supervisor.state(EMBEDDING) is ServerState.READY


def test_fourth_end_fails(files, platform) -> None:
    supervisor = make(files, platform)
    supervisor.endpoint(EMBEDDING)
    for _ in range(3):
        platform.started[-1].code = 1
        supervisor.endpoint(EMBEDDING)
    platform.started[-1].code = 1

    with pytest.raises(ModelUnavailable, match=NOT_STARTED):
        supervisor.endpoint(EMBEDDING)
    assert supervisor.state(EMBEDDING) is ServerState.FAILED


def test_restart_keeps_the_device(files, platform) -> None:
    supervisor = make(files, platform, device=NVIDIA.name)
    supervisor.endpoint(CHAT)
    platform.started[-1].code = 1

    supervisor.endpoint(CHAT)

    assert [p.device for p in platform.started] == ["Vulkan1", "Vulkan1"]


def test_stop_ends_everything(files, platform) -> None:
    supervisor = make(files, platform)
    supervisor.endpoint(EMBEDDING)
    supervisor.endpoint(CHAT)

    supervisor.stop()

    assert all(p.code is not None for p in platform.started)
    assert platform.closed
    assert supervisor.state(CHAT) is ServerState.STOPPED


def test_missing_file(files, platform) -> None:
    files["chat"].unlink()

    with pytest.raises(ModelUnavailable, match=MISSING):
        make(files, platform).endpoint(CHAT)
    assert platform.started == []


def test_gpu_without_enough_dedicated_memory_is_skipped(files, platform) -> None:
    platform.device_list = [INTEL_SMALL, NVIDIA_4GB]
    chosen: list[str] = []

    make(files, platform, chosen=chosen).endpoint(CHAT)

    assert [p.device for p in platform.started] == ["Vulkan1"]
    assert platform.benchmarked == []
    assert chosen == [NVIDIA.name]


def test_unknown_memory_is_measured(files, platform) -> None:
    platform.device_list = [INTEL_SMALL, NVIDIA_4GB, Device("Vulkan2", "Other GPU")]
    platform.times = {"Vulkan1": 1.3, "Vulkan2": 2.0}

    make(files, platform).endpoint(CHAT)

    assert platform.benchmarked == ["Vulkan1", "Vulkan2"]


def test_no_gpu_fits_runs_on_cpu(files, platform) -> None:
    files["chat"].write_bytes(b"x" * 1024)
    platform.device_list = [INTEL_SMALL, Device("Vulkan1", NVIDIA.name, 100 * MIB)]

    make(files, platform).endpoint(CHAT)

    assert [p.device for p in platform.started] == ["cpu"]


def test_stored_device_that_no_longer_fits(files, platform) -> None:
    platform.device_list = [INTEL_SMALL, NVIDIA_4GB]
    chosen: list[str] = []

    make(files, platform, device=INTEL.name, chosen=chosen).endpoint(CHAT)

    assert [p.device for p in platform.started] == ["Vulkan1"]
    assert chosen == [NVIDIA.name]


def test_with_memory_matches_names() -> None:
    memory = {"intel(r) iris(r) xe graphics": 128 * MIB}

    assert with_memory([INTEL, NVIDIA], memory) == [INTEL_SMALL, NVIDIA]


def test_dedicated_memory_reads_windows() -> None:
    memory = dedicated_memory()

    assert all(isinstance(size, int) and size >= 0 for size in memory.values())


def test_parse_devices() -> None:
    text = (
        "Available devices:\n"
        "  Vulkan0: Intel(R) Iris(R) Xe Graphics (8044 MiB, 7385 MiB free)\n"
        "  Vulkan1: NVIDIA GeForce RTX 3050 Ti Laptop GPU (3962 MiB, 3359 MiB free)\n"
    )

    assert parse_devices(text) == [INTEL, NVIDIA]


def test_parse_no_devices() -> None:
    assert parse_devices("Available devices:\n") == []
