# PyInstaller build of Cognia, one folder: task build.
#
# The result is dist/Cognia/: Cognia.exe, _internal/, and models/ beside the exe,
# because the model paths in config.json are taken from the folder of the exe.

import json
import shutil
from pathlib import Path

import pefile
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH)
SRC = ROOT / "src"
BUILD = ROOT / "build"

# The installed form keeps the database in the user's data folder, not in a
# folder beside the program.
defaults = json.loads((SRC / "config.json").read_text(encoding="utf-8"))
defaults["DATABASE_PATH"] = None
BUILD.mkdir(exist_ok=True)
shipped_config = BUILD / "config.json"
shipped_config.write_text(json.dumps(defaults, indent=2), encoding="utf-8")

datas = [
    (str(SRC / "resources"), "src/resources"),
    (str(shipped_config), "src"),
    # Alembic reads the revisions from files, not from imported modules.
    (
        str(SRC / "infrastructure" / "storage" / "migrations"),
        "src/infrastructure/storage/migrations",
    ),
    *collect_data_files("espeakng_loader"),
    *collect_data_files("kokoro_onnx"),
]

a = Analysis(
    [str(SRC / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=collect_dynamic_libs("espeakng_loader"),
    datas=datas,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Cognia",
    icon=str(SRC / "resources" / "logo.ico"),
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Cognia")

MODELS = ROOT / "models"
SERVERS = {
    "cpu": "llama-server.exe",
    "vulkan": "llama-server.exe",
    "whisper": "whisper-server.exe",
}
# The servers need the C++ runtime, which a clean Windows does not have.
# Installing it needs administrator rights, so a copy sits beside each server.
VC_REDIST = Path(
    r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
    r"\VC\Redist\MSVC\14.44.35112\x64"
)
VC_DLLS = (
    "Microsoft.VC143.CRT/msvcp140.dll",
    "Microsoft.VC143.CRT/vcruntime140.dll",
    "Microsoft.VC143.CRT/vcruntime140_1.dll",
    "Microsoft.VC143.OpenMP/vcomp140.dll",
)
_IMPORTS = [
    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
]


def server_files(folder, exe):
    """The server, the DLLs it imports, the ggml backends it loads by name at
    run time, and the licence files. The other tools of the release are left
    out."""
    files = {path.name.lower(): path for path in folder.iterdir()}
    needed, todo = set(), [exe.lower()]
    while todo:
        name = todo.pop()
        if name in needed or name not in files:
            continue
        needed.add(name)
        pe = pefile.PE(str(files[name]), fast_load=True)
        pe.parse_data_directories(directories=_IMPORTS)
        for table in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
            todo += [entry.dll.decode().lower() for entry in getattr(pe, table, [])]
    return [
        path
        for name, path in files.items()
        if name in needed
        or (name.startswith("ggml-") and name.endswith(".dll"))
        or path.suffix.lower() not in (".exe", ".dll")
    ]


target = Path(DISTPATH) / "Cognia" / "models"
shutil.copytree(
    MODELS, target, ignore=shutil.ignore_patterns("runtime"), dirs_exist_ok=True
)
for folder, exe in SERVERS.items():
    destination = target / "runtime" / folder
    destination.mkdir(parents=True, exist_ok=True)
    for path in server_files(MODELS / "runtime" / folder, exe):
        shutil.copy2(path, destination)
    for dll in VC_DLLS:
        shutil.copy2(VC_REDIST / dll, destination)
