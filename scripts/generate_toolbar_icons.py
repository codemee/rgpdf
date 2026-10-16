# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Export README icons using the application's actual toolbar painter."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from rgpdf.app import apply_application_theme
from rgpdf.buttons import SettingsButton


def main() -> None:
    app = QApplication([])
    apply_application_theme(app, "light")
    destination = Path(__file__).resolve().parents[1] / "docs" / "toolbar"
    destination.mkdir(parents=True, exist_ok=True)
    for kind in (
        "recursive", "scope_pdf", "scope_word", "scope_all", "case", "regex",
        "highlighter", "cache", "language_system", "language_zh", "language_en",
        "theme_system", "sun", "moon", "about",
        "browse", "search", "cancel", "help", "custom_color",
        "previous_page", "next_page", "zoom_out", "zoom_in", "fit_width", "fit_page",
    ):
        button = SettingsButton()
        button.set_icon_kind(kind)
        if kind == "highlighter":
            button.icon_foreground = QColor("#e6a323")
        button.ensurePolished()
        pixmap = QPixmap(68, 68)
        pixmap.setDevicePixelRatio(2)
        pixmap.fill(Qt.GlobalColor.transparent)
        button.render(pixmap)
        if not pixmap.save(str(destination / f"{kind}.png")):
            raise RuntimeError(f"Could not save {kind}")
        button.close()


if __name__ == "__main__":
    main()
