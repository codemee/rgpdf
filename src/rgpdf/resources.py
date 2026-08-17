# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from importlib.resources import files

from PySide6.QtGui import QIcon


def application_icon() -> QIcon:
    icon_path = files("rgpdf").joinpath("assets", "rgpdf.svg")
    return QIcon(str(icon_path))
