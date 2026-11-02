# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from importlib.resources import files
from functools import lru_cache

from PySide6.QtGui import QIcon
from PySide6.QtSvg import QSvgRenderer


def application_icon() -> QIcon:
    icon_path = files("rgpdf").joinpath("assets", "rgpdf.svg")
    return QIcon(str(icon_path))


@lru_cache(maxsize=2)
def pdf_logo(*, disabled: bool = False) -> QSvgRenderer:
    artwork = files("rgpdf.assets").joinpath("acrobat.svg").read_bytes()
    if disabled:
        artwork = artwork.replace(b'fill="#FA0F00"', b'fill="#f7a39c"')
    return QSvgRenderer(artwork)
