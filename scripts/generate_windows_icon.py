# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

"""Generate a multi-resolution Windows ICO from the application's SVG."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError(f"Unable to encode the {size}px icon")
    return bytes(data)


def build_ico(svg_path: Path, output_path: Path) -> None:
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise ValueError(f"Invalid SVG: {svg_path}")

    images = [(size, render_png(renderer, size)) for size in ICON_SIZES]
    header_size = 6 + 16 * len(images)
    entries = bytearray()
    payload = bytearray()
    offset = header_size
    for size, png in images:
        dimension = 0 if size == 256 else size
        entries.extend(
            struct.pack(
                "<BBBBHHII",
                dimension,
                dimension,
                0,
                0,
                1,
                32,
                len(png),
                offset,
            )
        )
        payload.extend(png)
        offset += len(png)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(
        struct.pack("<HHH", 0, 1, len(images)) + entries + payload
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path, default=Path("src/rgpdf/assets/rgpdf.svg")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("build-assets/rgpdf.ico")
    )
    args = parser.parse_args()
    QGuiApplication([])
    build_ico(args.source, args.output)


if __name__ == "__main__":
    main()
