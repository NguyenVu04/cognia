"""Entry point: ``uv run python -m src`` from ``desktop/``."""

import sys

from src.app.application import main

if __name__ == "__main__":
    sys.exit(main())
