"""Entry point: ``uv run python -m src`` from ``desktop/``, or this file run
directly, as the start line of Windows does."""

import sys
from pathlib import Path

if not __package__:
    # Run as a file, the package root is not on the path yet.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app.application import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
