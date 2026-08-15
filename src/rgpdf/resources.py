from __future__ import annotations

from importlib.resources import files

from PySide6.QtGui import QIcon


def application_icon() -> QIcon:
    icon_path = files("rgpdf").joinpath("assets", "rgpdf.svg")
    return QIcon(str(icon_path))

