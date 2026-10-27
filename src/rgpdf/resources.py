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


@lru_cache(maxsize=1)
def pdf_logo() -> QSvgRenderer:
    return QSvgRenderer(files("rgpdf.assets").joinpath("acrobat.svg").read_bytes())
