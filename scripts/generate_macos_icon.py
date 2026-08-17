# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE = PROJECT_ROOT / "src" / "rgpdf" / "assets" / "rgpdf.svg"
OUTPUT = PROJECT_ROOT / "build-assets" / "rgpdf.icns"
ICON_SIZES = ((16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2))


def render_png(renderer: QSvgRenderer, output: Path, logical_size: int, scale: int) -> None:
    pixels = logical_size * scale
    image = QImage(pixels, pixels, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()
    if not image.save(str(output), "PNG"):
        raise RuntimeError(f"Unable to write {output}")


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("This icon generator must run on macOS (iconutil is required).")
    if shutil.which("iconutil") is None:
        raise SystemExit("iconutil was not found; install the macOS command-line tools.")
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        raise SystemExit(f"Unable to load SVG icon: {SOURCE}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rgpdf-icon-") as temporary:
        iconset = Path(temporary) / "rgpdf.iconset"
        iconset.mkdir()
        for size, scale in ICON_SIZES:
            suffix = "@2x" if scale == 2 else ""
            render_png(renderer, iconset / f"icon_{size}x{size}{suffix}.png", size, scale)
        subprocess.run(["iconutil", "--convert", "icns", "--output", str(OUTPUT), str(iconset)], check=True)
    print(f"Generated {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
