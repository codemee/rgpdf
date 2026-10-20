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
import pytest


def test_main_window_has_three_result_columns(qtbot, monkeypatch, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("appearance/language", "en")
    applied_themes = []
    window = MainWindow(applied_themes.append, settings=settings)
    qtbot.addWidget(window)
    assert window.windowTitle() == f"rgPDF {__version__} — Document Search"
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
        window.scope_button,
        window.regex_button,
        window.line_wrap_button,
        window.highlight_button,
        window.cache_button,
        window.about_button,
    )
    assert all(isinstance(button, SettingsButton) for button in settings_buttons)
    assert all(button.size() == QSize(34, 34) for button in settings_buttons)
    assert all(button.iconSize() == QSize(20, 20) for button in settings_buttons)
    assert all(button.contentsMargins() == QMargins(4, 4, 4, 4) for button in settings_buttons)
    assert isinstance(window.settings_toolbar, QToolBar)
    assert window.settings_toolbar.layout().spacing() == 4
    assert len(window.settings_toolbar.findChildren(SettingsButton)) == 10
    toolbar_buttons = [
        widget
        for action in window.settings_toolbar.actions()
        if isinstance(
            (widget := window.settings_toolbar.widgetForAction(action)), SettingsButton
        )
    ]
    assert toolbar_buttons == [
        window.recursive_button,
        window.scope_button,
        window.case_button,
        window.regex_button,
        window.line_wrap_button,
        window.highlight_button,
        window.cache_button,
        window.language_button,
        window.theme_button,
        window.about_button,
    ]
    assert window.left_panel is window.main_splitter.widget(0)
    expected_alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    assert window.search_form.labelAlignment() == expected_alignment
    assert window.folder_label.alignment() == expected_alignment
    assert window.pattern_label.alignment() == expected_alignment
    assert window.search_form.itemAt(2, window.search_form.ItemRole.FieldRole).widget().layout().contentsMargins().isNull()
    assert window.search_form.itemAt(0, window.search_form.ItemRole.FieldRole).widget().layout().contentsMargins().isNull()
    assert window.search_scope == "pdf"
    assert window.scope_button.icon_kind == "scope_pdf"
    window.scope_button.click()
    assert window.search_scope == "word"
    assert window.scope_button.icon_kind == "scope_word"
    window.scope_button.click()
    assert window.search_scope == "all"
    assert window.scope_button.icon_kind == "scope_all"
    settings.sync()
    assert settings.value("search/scope") == "all"
    assert window.pattern_help_button.text() == ""
    assert window.about_button.icon_kind == "about"
    assert window.cache_button.icon_kind == "cache"
    assert window.cache_button.toolTip() == "Clear Word cache"
    action_labels = (
        (window.browse_button, "Browse…"),
        (window.search_button, "Search"),
        (window.cancel_button, "Cancel"),
        (window.custom_color_button, "Custom color…"),
        (window.pattern_help_button, "Search pattern help"),
        (window.preview.previous_button, "Previous page"),
        (window.preview.next_button, "Next page"),
        (window.preview.zoom_out_button, "Zoom out"),
        (window.preview.zoom_in_button, "Zoom in"),
        (window.preview.fit_button, "Fit width"),
        (window.preview.fit_page_button, "Fit page"),
    )
    for button, label in action_labels:
        assert button.text() == ""
        assert button.toolTip() == label
        assert button.accessibleName() == label
        assert button.icon_kind
    about_calls = []
    monkeypatch.setattr(
        "rgpdf.main_window.QMessageBox.about",
        lambda parent, title, content: about_calls.append((parent, title, content)),
    )
    window.about_button.click()
    assert about_calls[0][0] is window
    assert about_calls[0][1] == "About rgPDF"
    assert f"tree/v{__version__}" in about_calls[0][2]
    assert "GNU Affero General Public License" in about_calls[0][2]
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


def test_line_wrap_option_persists_and_is_disabled_during_search(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / "wrap.ini"), QSettings.Format.IniFormat)
    settings.setValue("appearance/language", "en")
    window = MainWindow(lambda theme: None, settings=settings)
    qtbot.addWidget(window)
    assert not window.line_wrap_button.isChecked()
    assert window.line_wrap_button.toolTip().startswith("Ignore layout line wraps")
    assert window.line_wrap_button.icon_kind == "line_wrap"
    window.line_wrap_button.click()
    assert window._options().ignore_line_wraps
    window._set_searching(True)
    assert not window.line_wrap_button.isEnabled()
    window._set_searching(False)
    window.close()
    reopened = MainWindow(lambda theme: None, settings=settings)
    qtbot.addWidget(reopened)
    assert reopened.line_wrap_button.isChecked()
    reopened.language = "zh_TW"
    reopened.retranslate_ui()
    assert reopened.line_wrap_button.toolTip().startswith("忽略排版換行")
    reopened.close()


def test_folder_and_filter_changes_do_not_convert_word(qtbot, monkeypatch, tmp_path):
    conversions = []
    monkeypatch.setattr("rgpdf.search.convert_word_to_pdf", lambda *args, **kwargs: conversions.append(args))
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(lambda theme: None, settings=settings)
    qtbot.addWidget(window)
    (tmp_path / "sample.docx").touch()
    window.folder_edit.setText(str(tmp_path))
    window._cycle_search_scope()
    window.stem_filter_edit.setText("sample*")
    window.recursive_button.setChecked(False)
    qtbot.wait(350)
    assert conversions == []
    assert window.worker is None
    assert window.cache_button.isEnabled()
    window.close()


def test_stem_filter_searches_matching_files_and_persists(qtbot, tmp_path):
    for name in ("ch01.pdf", "ch02.pdf", "ch1.pdf", "ch2.pdf"):
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((72, 72), "needle")
            document.save(tmp_path / name)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("appearance/language", "en")
    window = MainWindow(lambda theme: None, settings=settings)
    qtbot.addWidget(window)
    assert window.stem_filter_edit.text() == ""
    assert window.search_form.itemAt(1, window.search_form.ItemRole.FieldRole).widget().layout().indexOf(window.stem_filter_edit) == 1
    assert window.stem_filter_label.text() == "Filename stem filter"
    assert window.stem_filter_help_button.toolTip() == "Filename stem filter help"
    assert window.stem_filter_help_button.accessibleName() == "Filename stem filter help"
    assert window.stem_filter_help_button.icon_kind == "help"
    assert "<code>ch0*</code>" in window.stem_filter_help_content.text()
    assert "<code>[!abc]</code>" in window.stem_filter_help_content.text()
    assert "Leave empty for no filter" in window.stem_filter_help_content.text()
    window.show()
    qtbot.mouseClick(window.stem_filter_help_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(window.stem_filter_help_menu.isVisible)
    window.stem_filter_help_menu.close()
    window.language = "zh_TW"
    window.retranslate_ui()
    assert window.stem_filter_help_button.toolTip() == "主檔名篩選說明"
    assert "留空時不篩選" in window.stem_filter_help_content.text()
    window.folder_edit.setText(str(tmp_path))
    window.pattern_edit.setText("needle")
    window.stem_filter_edit.setText("ch0*")
    window._start_search()
    assert not window.stem_filter_edit.isEnabled()
    qtbot.waitUntil(lambda: window.worker is None, timeout=5000)
    assert window.stem_filter_edit.isEnabled()
    assert [doc.path.name for doc in window.documents] == ["ch01.pdf", "ch02.pdf"]
    window.close()
    qtbot.waitUntil(lambda: not window.preview._workers, timeout=5000)
    settings.sync()
    assert settings.value("search/stem_glob") == "ch0*"

    reopened = MainWindow(lambda theme: None, settings=settings)
    qtbot.addWidget(reopened)
    assert reopened.stem_filter_edit.text() == "ch0*"
    assert reopened._options().stem_glob == "ch0*"
    reopened.stem_filter_edit.clear()
    reopened.stem_filter_edit.returnPressed.emit()
    qtbot.waitUntil(lambda: reopened.worker is None, timeout=5000)
    assert [doc.path.name for doc in reopened.documents] == [
        "ch01.pdf", "ch02.pdf", "ch1.pdf", "ch2.pdf"
    ]
    assert settings.value("search/stem_glob") == ""
    reopened.close()
    qtbot.waitUntil(lambda: not reopened.preview._workers, timeout=5000)


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


@pytest.mark.parametrize("page_size", [(595, 842), (842, 595), (6000, 9000)])
def test_fit_page_shows_entire_page_and_tracks_resize(qtbot, tmp_path, page_size):
    path = tmp_path / "fit-page.pdf"
    with fitz.open() as document:
        document.new_page(width=page_size[0], height=page_size[1])
        document.new_page(width=page_size[1], height=page_size[0])
        document.save(path)
    match = TextMatch(
        matched_text="match", context="match", start=0, end=5,
        start_page=0, end_page=0, highlights=(),
    )
    preview = PdfPreview()
    qtbot.addWidget(preview)
    preview.set_language("zh_TW")
    assert preview.fit_page_button.toolTip() == "符合頁面"
    assert not preview.fit_page_button.isEnabled()
    preview.set_language("en")
    assert preview.fit_page_button.toolTip() == "Fit page"
    preview.resize(700, 650)
    preview.show()
    preview.show_match(str(path), match)
    qtbot.waitUntil(lambda: not preview._workers, timeout=5000)
    preview.fit_page_button.click()

    def entire_page_visible():
        image = preview.image_label.pixmap()
        viewport = preview.scroll_area.viewport()
        return (
            not preview._resize_timer.isActive()
            and not preview._workers
            and not image.isNull()
            and image.width() <= viewport.width()
            and image.height() <= viewport.height()
            and preview.scroll_area.horizontalScrollBar().maximum() == 0
            and preview.scroll_area.verticalScrollBar().maximum() == 0
        )

    qtbot.waitUntil(entire_page_visible, timeout=5000)
    original_size = preview.image_label.pixmap().size()
    preview.resize(600, 400)
    qtbot.waitUntil(entire_page_visible, timeout=5000)
    assert preview.image_label.pixmap().size() != original_size
    preview.next_button.click()
    qtbot.waitUntil(entire_page_visible, timeout=5000)
    preview.fit_button.click()
    qtbot.waitUntil(lambda: not preview._workers, timeout=5000)
    width_zoom = preview._zoom
    preview.zoom_in_button.click()
    qtbot.waitUntil(lambda: not preview._workers, timeout=5000)
    assert preview._zoom > width_zoom
    preview.fit_page_button.click()
    qtbot.waitUntil(entire_page_visible, timeout=5000)
    preview.clear()
    assert not preview.fit_page_button.isEnabled()
    preview.close()


@pytest.mark.parametrize("page_count,start_page", [(1, 0), (3, 0), (3, 1), (3, 2)])
def test_preview_browses_all_pages_and_resets_for_selection(
    qtbot, tmp_path, page_count, start_page
) -> None:
    path = tmp_path / "navigation.pdf"
    with fitz.open() as document:
        for index in range(page_count):
            page = document.new_page()
            page.insert_text((72, 72), f"Page {index + 1}")
        document.save(path)
    match = TextMatch(
        matched_text="Page",
        context="Page",
        start=0,
        end=4,
        start_page=start_page,
        end_page=start_page,
        highlights=(PageHighlight(start_page, ((72.0, 60.0, 105.0, 75.0),)),),
    )
    preview = PdfPreview()
    qtbot.addWidget(preview)
    preview.set_language("en")
    assert not preview.previous_button.isEnabled()
    assert not preview.next_button.isEnabled()
    assert preview.previous_button.toolTip() == "Previous page"
    assert preview.next_button.toolTip() == "Next page"
    preview.show_match(str(path), match)

    def check_page(index):
        qtbot.waitUntil(lambda: not preview._workers, timeout=5000)
        assert not preview.image_label.pixmap().isNull()
        assert preview.page_label.text() == f"Page {index + 1} of {page_count}"
        assert preview.previous_button.isEnabled() == (index > 0)
        assert preview.next_button.isEnabled() == (index < page_count - 1)

    check_page(start_page)
    for index in range(start_page - 1, -1, -1):
        preview.previous_button.click()
        check_page(index)
    preview.previous_button.click()
    check_page(0)
    for index in range(1, page_count):
        preview.next_button.click()
        check_page(index)
    preview.next_button.click()
    check_page(page_count - 1)
    # Several navigation requests may be in flight when another match is selected.
    for _ in range(page_count - 1):
        preview.previous_button.click()
    preview.show_match(str(path), match)
    check_page(start_page)
    preview.next_button.click()
    preview.clear()
    qtbot.waitUntil(lambda: not preview._workers, timeout=5000)
    assert preview.page_label.text() == ""
    assert preview.image_label.pixmap().isNull()
    assert not preview.previous_button.isEnabled()
    assert not preview.next_button.isEnabled()
    preview.close()
