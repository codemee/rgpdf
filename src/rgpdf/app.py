# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import sys
import multiprocessing

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from rgpdf.main_window import MainWindow
from rgpdf.buttons import SettingsButton
from rgpdf.resources import application_icon
from rgpdf.word_conversion import cleanup_word_cache


BASE_STYLE = """
QWidget { font-size: 13px; color: palette(window-text); }
QMainWindow, QWidget#centralWidget, QMenuBar, QMenu { background: palette(window); }
QToolBar#settingsToolbar {
    background: palette(alternate-base);
    border: 0;
    border-bottom: 1px solid palette(mid);
    padding: 0;
    spacing: 4px;
}
QToolBar#settingsToolbar::separator {
    background: palette(mid);
    width: 1px;
    margin: 7px 6px;
}
QLineEdit, QTreeWidget, QScrollArea {
    border: 1px solid palette(mid);
    border-radius: 5px;
    padding: 5px;
    background: palette(base);
}
QToolButton {
    border: 0;
    border-radius: __TOOL_BUTTON_RADIUS__;
    background: transparent;
}
QToolButton:hover { background: palette(midlight); }
QToolButton:pressed { background: palette(mid); }
QToolButton:checked {
    background: palette(midlight);
    border: 0;
}
QPushButton {
    border: 0;
    border-radius: 7px;
    padding: 6px 12px;
    background: palette(button);
}
QPushButton:hover { background: palette(midlight); }
QPushButton:pressed { background: palette(midlight); }
QPushButton:disabled { color: palette(mid); }
QGroupBox {
    border: 1px solid palette(mid);
    border-radius: 7px;
    margin-top: 10px;
    padding-top: 7px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 9px; padding: 0 4px; }
QFrame#highlightPanel {
    background: palette(alternate-base);
    border: 1px solid palette(mid);
    border-radius: 6px;
}
QGroupBox#searchArea {
    background: palette(alternate-base);
}
QHeaderView::section {
    background: palette(alternate-base);
    color: palette(text);
    border: 0;
    border-bottom: 1px solid palette(mid);
    padding: 5px 7px;
    font-weight: 600;
}
QProgressBar { border: 0; border-radius: 3px; text-align: center; min-width: 240px; }
QProgressBar::chunk { background: palette(highlight); border-radius: 3px; }
QSplitter::handle { background: transparent; }
QStatusBar {
    background: palette(alternate-base);
    border-top: 1px solid palette(mid);
}
QStatusBar::item { border: 0; }
QStatusBar QLabel { padding: 2px 4px; }
""".replace("__TOOL_BUTTON_RADIUS__", f"{SettingsButton.CORNER_RADIUS:g}px")


DARK_STYLE = """
QGroupBox::title { color: #b6f53c; }
QLineEdit:focus { border: 1px solid #ffad66; }
QToolButton:pressed { background: #594078; }
QToolTip {
    background: #30223f;
    color: #eee8f7;
    border: 1px solid #755694;
    padding: 5px;
}
"""


def _light_palette(app: QApplication) -> QPalette:
    palette = app.style().standardPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f5f6f8"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#eef0f3"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#475569"))
    palette.setColor(QPalette.ColorRole.Mid, QColor("#c8ced8"))
    palette.setColor(QPalette.ColorRole.Midlight, QColor("#e2e6ed"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#718096"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#3578e5"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return palette


def _dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#191320"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#eee8f7"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#21192d"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#2d203d"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#30223f"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#eee8f7"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#eee8f7"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#39274e"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#eee8f7"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#ffad66"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#b6f53c"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#191320"))
    palette.setColor(QPalette.ColorRole.Accent, QColor("#b6f53c"))
    palette.setColor(QPalette.ColorRole.Mid, QColor("#67517d"))
    palette.setColor(QPalette.ColorRole.Midlight, QColor("#483263"))
    palette.setColor(QPalette.ColorRole.Dark, QColor("#120e19"))
    palette.setColor(QPalette.ColorRole.Shadow, QColor("#0d0911"))
    palette.setColor(QPalette.ColorRole.Light, QColor("#8264a5"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#b4a1d2"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText, QPalette.ColorRole.PlaceholderText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#776888"))
    return palette


def apply_application_theme(app: QApplication, theme: str) -> None:
    selected = theme
    if theme == "system":
        scheme = app.styleHints().colorScheme()
        selected = "dark" if scheme == Qt.ColorScheme.Dark else "light"
    app.setPalette(_dark_palette() if selected == "dark" else _light_palette(app))
    # Qt caches palette() values referenced by stylesheets, so force a full repolish.
    app.setStyleSheet("")
    app.setStyleSheet(BASE_STYLE + (DARK_STYLE if selected == "dark" else ""))
    for widget in app.topLevelWidgets():
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


def main() -> int:
    multiprocessing.freeze_support()
    cleanup_word_cache()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("rgPDF")
    app.setApplicationDisplayName("rgPDF")
    app.setOrganizationName("rgpdf")
    app.setWindowIcon(application_icon())
    app.setStyle("Fusion")
    app.setStyleSheet(BASE_STYLE)

    def apply_theme(theme: str) -> None:
        apply_application_theme(app, theme)

    settings = QSettings("rgpdf", "rgpdf")
    apply_theme(settings.value("appearance/theme", "system", type=str))
    window = MainWindow(apply_theme)
    app.styleHints().colorSchemeChanged.connect(
        lambda _scheme: apply_theme("system")
        if settings.value("appearance/theme", "system", type=str) == "system"
        else None
    )
    window.show()
    return app.exec()
