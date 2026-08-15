from __future__ import annotations

from PySide6.QtCore import QMargins, QSettings, QSize, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QToolBar

from rgpdf import __version__
from rgpdf.app import apply_application_theme
from rgpdf.main_window import MainWindow, SettingsButton
from rgpdf.models import PageHighlight, TextMatch
from rgpdf.preview import PdfPreview
from rgpdf.resources import application_icon

import pymupdf as fitz


def test_main_window_has_three_result_columns(qtbot, monkeypatch, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("appearance/language", "en")
    applied_themes = []
    window = MainWindow(applied_themes.append, settings=settings)
    qtbot.addWidget(window)
    assert window.windowTitle() == f"rgpdf {__version__} — PDF Search"
    assert window.main_splitter.count() == 2
    assert window.main_splitter.handleWidth() == 12
    assert window.main_splitter.widget(1) is window.preview_group
    assert window.result_splitter.count() == 2
    assert window.result_splitter.handleWidth() == 10
    assert window.file_list.columnCount() == 2
    assert window.match_list.columnCount() == 2
    assert window.file_list.headerItem().text(0)
    assert window.file_list.headerItem().text(1)
    settings_buttons = (
        window.language_button,
        window.theme_button,
        window.recursive_button,
        window.case_button,
        window.regex_button,
        window.highlight_button,
    )
    assert all(isinstance(button, SettingsButton) for button in settings_buttons)
    assert all(button.size() == QSize(34, 34) for button in settings_buttons)
    assert all(button.iconSize() == QSize(20, 20) for button in settings_buttons)
    assert all(button.contentsMargins() == QMargins(4, 4, 4, 4) for button in settings_buttons)
    assert isinstance(window.settings_toolbar, QToolBar)
    assert len(window.settings_toolbar.findChildren(SettingsButton)) == 6
    assert window.left_panel is window.main_splitter.widget(0)
    expected_alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    assert window.search_form.labelAlignment() == expected_alignment
    assert window.folder_label.alignment() == expected_alignment
    assert window.pattern_label.alignment() == expected_alignment
    assert window.search_form.itemAt(1, window.search_form.ItemRole.FieldRole).widget().layout().contentsMargins().isNull()
    assert window.search_form.itemAt(0, window.search_form.ItemRole.FieldRole).widget().layout().contentsMargins().isNull()
    assert window.pattern_help_button.text() == "?"
    assert window.pattern_help_button.menu() is None
    assert window.pattern_help_content.openExternalLinks()
    assert "Regular Expression" in window.pattern_help_content.text()
    assert '<a href="https://github.com/mrabarnett/mrab-regex#readme">' in window.pattern_help_content.text()
    assert window.regex_button.isChecked()
    assert window.language_button.icon_kind == "language_en"
    window.language_button.click()
    settings.sync()
    assert window.language_preference == "system"
    assert settings.value("appearance/language") == "system"
    assert window.language_button.icon_kind == "language_system"
    assert window.theme_preference == "system"
    window.theme_button.click()
    assert window.theme_preference == "light"
    assert applied_themes == ["light"]
    window.theme_button.click()
    assert window.theme_preference == "dark"
    assert window.theme_button.icon_kind == "moon"
    window.case_button.setChecked(True)
    window.recursive_button.setChecked(False)
    settings.sync()
    assert settings.value("search/case_sensitive", type=bool) is True
    assert settings.value("search/recursive", type=bool) is False
    window.regex_button.setChecked(False)
    settings.sync()
    assert settings.value("search/use_regex", type=bool) is False
    assert not window.highlight_panel.isVisible()
    window.highlight_button.setChecked(True)
    assert not window.highlight_panel.isHidden()
    window._set_highlight_color("#7dddf2")
    assert window.highlight_panel.isHidden()
    assert window.highlight_button.styleSheet() == ""
    assert window.highlight_button.icon_foreground.name() == "#7dddf2"
    assert window.highlight_button.icon_kind == "highlighter"
    settings.sync()
    assert settings.value("appearance/highlight_color") == "#7dddf2"
    assert window.preview._highlight_color == "#7dddf2"
    window.pattern_edit.setText(r"saved\s+pattern")
    window.pattern_edit.editingFinished.emit()
    settings.sync()
    assert settings.value("search/pattern") == r"saved\s+pattern"
    window.close()


def test_theme_switch_recolors_entire_application(qapp) -> None:
    apply_application_theme(qapp, "dark")
    dark = qapp.palette().color(QPalette.ColorRole.Window)
    apply_application_theme(qapp, "light")
    light = qapp.palette().color(QPalette.ColorRole.Window)
    assert dark.name() == "#202124"
    assert light.name() == "#f5f6f8"


def test_application_icon_is_available() -> None:
    icon = application_icon()
    assert not icon.isNull()
    assert not icon.pixmap(64, 64).isNull()


def test_preview_renders_selected_match_asynchronously(qtbot, tmp_path) -> None:
    path = tmp_path / "preview.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "match")
    document.save(path)
    document.close()
    match = TextMatch(
        matched_text="match",
        context="match",
        start=0,
        end=5,
        start_page=0,
        end_page=0,
        highlights=(PageHighlight(0, ((72.0, 60.0, 105.0, 75.0),)),),
    )
    preview = PdfPreview()
    qtbot.addWidget(preview)
    preview.resize(500, 600)
    preview.show()
    preview.show_match(str(path), match)
    qtbot.waitUntil(lambda: not preview.image_label.pixmap().isNull(), timeout=5000)
    assert not preview.image_label.pixmap().isNull()
    preview.close()
