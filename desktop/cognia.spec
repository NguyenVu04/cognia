# PyInstaller build of Cognia, one folder: task build.
#
# The result is dist/Cognia/: Cognia.exe, _internal/, and models/ beside the exe,
# because the model paths in config.json are taken from the folder of the exe.

import json
import shutil
from pathlib import Path

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

shutil.copytree(
    ROOT / "models", Path(DISTPATH) / "Cognia" / "models", dirs_exist_ok=True
)
