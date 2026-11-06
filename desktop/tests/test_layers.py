"""Rules about which code may import what, checked on the source."""

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
_LANGCHAIN = ("langchain", "langgraph", "langsmith", "openai")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_langchain_only_in_ai() -> None:
    allowed = SRC / "infrastructure" / "ai"
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if allowed not in path.parents
        and any(name.split(".")[0].startswith(_LANGCHAIN) for name in _imports(path))
    ]

    assert offenders == []


def test_tool_loop_not_imported_at_start() -> None:
    # Importing the application must not import LangGraph; it loads later, on
    # the model thread.
    code = (
        "import sys; import src.app.application; "
        "print('langgraph' in sys.modules or 'langchain_core' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=SRC.parent, timeout=120,
    )

    assert result.stdout.strip() == "False", result.stderr
