# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Process-local handshake for the experimental Windows cache launcher."""

import os
from pathlib import Path
import sys


def launcher_path() -> Path | None:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None
    value = os.environ.get("RGPDF_LAUNCHER_PATH", "")
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() and path.suffix.lower() == ".exe" and path.is_file() else None


def mark_window_ready() -> None:
    value = os.environ.pop("RGPDF_STARTUP_MARKER", "")
    if not value or launcher_path() is None:
        return
    try:
        path = Path(value)
        expected = Path(os.environ["LOCALAPPDATA"]) / "rgpdf" / "logs" / "cached-launcher"
        if path.parent.resolve() == expected.resolve() and path.suffix == ".ready":
            path.write_text(str(os.getpid()), encoding="ascii")
    except (OSError, KeyError):
        pass  # Diagnostics must not prevent the main window from opening.
