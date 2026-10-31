"""Every Qt test runs without a display."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
