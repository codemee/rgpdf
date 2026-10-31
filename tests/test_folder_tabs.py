from threading import Event, Thread
from zipfile import ZipFile

import pymupdf as fitz
import pytest
from PySide6.QtCore import QPoint, QRect, QSettings, Qt
from PySide6.QtWidgets import QMessageBox, QTabBar
from PySide6.QtGui import QPalette, QPixmap

from rgpdf import word_conversion
from rgpdf.app import apply_application_theme
from rgpdf.conversion_service import WordConversionService
from rgpdf.export_dialog import WordExportDialog
from rgpdf.folder_tab import FolderTab
from rgpdf.main_window import MainWindow
from rgpdf.models import PreliminaryDocument, SearchOptions
from rgpdf.search import search_folder
from rgpdf.word_text import preliminary_document


def _docx(path, text='needle first paragraph', second='other paragraph'):
    with ZipFile(path, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p><w:p><w:r><w:t>' + second + '</w:t></w:r></w:p></w:body></w:document>')
    return path


def _pdf(path, text='needle'):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), text)
        doc.save(path)


def _window(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / 'session.ini'), QSettings.Format.IniFormat)
    settings.setValue('appearance/language', 'en')
    window = MainWindow(lambda _: None, settings)
    qtbot.addWidget(window)
    window.show()
    return window


def test_tab_identity_independent_conditions_and_restore(qtbot, tmp_path):
    a, b = tmp_path / 'a' / 'docs', tmp_path / 'b' / 'docs'
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    window = _window(qtbot, tmp_path)
    qtbot.wait(20)
    button = window.add_folder_button
    assert window.tabs.rect().contains(QRect(button.mapTo(window.tabs, QPoint(0, 0)), button.size()))
    assert button.parentWidget().rect().contains(button.geometry())
    first = window.open_folder(a)
    assert isinstance(first, FolderTab)
    first.pattern_edit.setText('first')
    first.stem_filter_edit.setText('ch0*')
    first.case_button.setChecked(True)
    second = window.open_folder(b)
    assert second.pattern_edit.text() == 'first'
    second.pattern_edit.setText('second')
    second.stem_filter_edit.setText('ch1*')
    second.case_button.setChecked(False)
    assert first.pattern_edit.text() == 'first' and first.case_button.isChecked()
    assert window.tabs.tabText(0) != window.tabs.tabText(1)
    assert window.open_folder(a / '.') is first
    assert window.tabs.count() == 2
    window.tabs.tabBar().moveTab(0, 1)
    window.tabs.setCurrentWidget(second)
    window.close()
    qtbot.waitUntil(lambda: not window.isVisible())
    reopened = MainWindow(lambda _: None, window.settings)
    qtbot.addWidget(reopened)
    assert reopened.tabs.count() == 2
    assert reopened.current_tab.folder_edit.text() == str(b.resolve())
    assert reopened.tabs.widget(0).pattern_edit.text() == 'second'
    assert reopened.tabs.widget(1).pattern_edit.text() == 'first'
    assert reopened.tabs.widget(1).case_button.isChecked()
    assert not reopened.tabs.widget(1).documents


def test_missing_folder_and_close_last_tab(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    missing = window.open_folder(tmp_path / 'missing')
    assert not missing.search_button.isEnabled() and not missing.export_word_button.isEnabled()
    assert 'missing' in missing.status_label.text().lower()
    window.close_tab(0)
    qtbot.waitUntil(lambda: missing not in window._pages)
    assert window.tabs.count() == 1 and not window.current_tab.folder_edit.text()
    blank = window.current_tab
    blank.shutdown()
    blank._start_search()
    blank._choose_word_export()
    assert blank.worker is None and blank.export_worker is None


def test_flat_tab_close_button_targets_reordered_folder(qtbot, tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir()
    b.mkdir()
    window = _window(qtbot, tmp_path)
    first = window.open_folder(a)
    second = window.open_folder(b)
    window.tabs.tabBar().moveTab(0, 1)
    index = window.tabs.indexOf(first)
    button = window.tabs.tabBar().tabButton(index, QTabBar.ButtonPosition.RightSide)
    assert button.icon_kind == 'close_tab'
    assert button.toolTip() == 'Close folder tab'
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: first not in window._pages)
    assert window.current_tab is second and window.tabs.count() == 1


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_inactive_tab_does_not_cover_content_border(qapp, qtbot, tmp_path, theme):
    apply_application_theme(qapp, theme)
    window = _window(qtbot, tmp_path)
    for name in ('first', 'second', 'third'):
        folder = tmp_path / name
        folder.mkdir()
        window.open_folder(folder)
    window.tabs.setCurrentIndex(0)
    qtbot.wait(20)
    bar = window.tabs.tabBar()
    pixmap = QPixmap(bar.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    bar.render(pixmap)
    image = pixmap.toImage()
    for index in range(bar.count()):
        rect = bar.tabRect(index)
        role = QPalette.ColorRole.Highlight if index == 0 else QPalette.ColorRole.Mid
        assert image.pixelColor(rect.center().x(), rect.bottom()) == bar.palette().color(role)


def test_preliminary_text_has_no_pages_and_keeps_paragraph_context(tmp_path):
    source = _docx(tmp_path / 'test.docx', 'prefix needle suffix', 'unrelated paragraph')
    result = preliminary_document(source, SearchOptions(tmp_path, 'needle'))
    assert result.matches[0].context == 'prefix needle suffix'
    assert not hasattr(result.matches[0], 'start_page')
    assert not preliminary_document(source, SearchOptions(tmp_path, 'NEEDLE', case_sensitive=True)).matches
    regex = preliminary_document(source, SearchOptions(tmp_path, r'n.e+dl.', use_regex=True))
    assert regex.matches[0].matched_text == 'needle'


def test_ready_pdfs_and_later_preliminary_results_bypass_blocked_word(qtbot, tmp_path, monkeypatch):
    source = _docx(tmp_path / 'a.docx')
    _docx(tmp_path / 'b.docx', 'needle later file')
    _pdf(tmp_path / 'ready.pdf')
    entered, release, done = Event(), Event(), Event()
    early, official, reports = [], [], []

    def convert(source, target, cancel):
        entered.set()
        assert release.wait(10)
        _pdf(target)

    monkeypatch.setattr(word_conversion, '_cache_root', lambda: tmp_path / 'cache')
    monkeypatch.setattr(word_conversion, 'available_converters', lambda: [('libreoffice', convert)])
    service = WordConversionService()

    def run():
        try:
            reports.append(search_folder(SearchOptions(tmp_path, 'needle', search_scope='all'),
                conversion_service=service, preliminary=early.append,
                document_found=lambda doc: official.append(doc.path.name)))
        finally:
            done.set()

    thread = Thread(target=run)
    thread.start()
    try:
        qtbot.waitUntil(lambda: entered.is_set() and len(early) == 2 and 'ready.pdf' in official)
        assert not done.is_set()
        assert [doc.path.name for doc in early] == ['a.docx', 'b.docx']
        release.set()
        qtbot.waitUntil(done.is_set)
        assert len(reports[0].documents) == 3
    finally:
        release.set()
        thread.join(10)
        service.close()
        qtbot.waitUntil(service.is_stopped)


def test_tabs_search_and_export_concurrently_with_waiting_preview(qtbot, tmp_path, monkeypatch):
    folders = [tmp_path / name for name in ('a', 'b', 'c')]
    for folder in folders:
        folder.mkdir()
    _docx(folders[0] / 'first.docx')
    _pdf(folders[1] / 'ready.pdf')
    _docx(folders[2] / 'export.docx')
    output = tmp_path / 'out'
    output.mkdir()
    entered, release = Event(), Event()
    calls = []

    def convert(source, target, cancel):
        calls.append(source.name)
        if source.name == 'first.docx':
            entered.set()
            assert release.wait(15)
        _pdf(target)

    monkeypatch.setattr(word_conversion, '_cache_root', lambda: tmp_path / 'cache')
    monkeypatch.setattr(word_conversion, 'available_converters', lambda: [('libreoffice', convert)])
    window = _window(qtbot, tmp_path)
    try:
        first = window.open_folder(folders[0])
        first.pattern_edit.setText('needle')
        first.search_scope = 'word'
        first._start_search()
        qtbot.waitUntil(lambda: entered.is_set() and bool(first.documents))
        assert isinstance(first.documents[0], PreliminaryDocument)
        assert first.preview.pages.currentWidget() is first.preview.waiting_page
        assert not first.preview.copy_page_button.isEnabled()
        second = window.open_folder(folders[1])
        second.search_scope = 'pdf'
        second._start_search()
        qtbot.waitUntil(lambda: second.worker is None and bool(second.documents), timeout=15000)
        assert first.worker is not None
        third = window.open_folder(folders[2])
        third.settings.setValue('export/folder', str(output))
        qtbot.waitUntil(lambda: third.export_word_button.isEnabled())
        monkeypatch.setattr(WordExportDialog, 'exec', lambda self: self.DialogCode.Accepted)
        third.export_word_button.click()
        qtbot.waitUntil(lambda: window.conversions.state(folders[2] / 'export.docx')[0] == 'queued')
        assert third.export_worker is not None and calls == ['first.docx']
        release.set()
        qtbot.waitUntil(lambda: first.worker is None and third.export_worker is None, timeout=15000)
        assert not isinstance(first.documents[0], PreliminaryDocument)
        assert first.preview.pages.currentWidget() is first.preview.scroll_area
        assert (output / 'export.pdf').is_file()
        assert [doc.path.name for doc in second.documents] == ['ready.pdf']
        window.tabs.setCurrentWidget(third)
        assert third.progress_bar.isHidden()
    finally:
        release.set()
        window.close()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=15000)


@pytest.mark.parametrize('outcome', ['miss', 'fail'])
def test_pdf_confirmation_removes_false_hits_or_shows_failure(qtbot, tmp_path, monkeypatch, outcome):
    root = tmp_path / 'docs'
    root.mkdir()
    _docx(root / 'candidate.docx')

    def convert(source, target, cancel):
        if outcome == 'fail':
            raise OSError('test renderer failure')
        _pdf(target, 'different content')

    monkeypatch.setattr(word_conversion, '_cache_root', lambda: tmp_path / 'cache')
    monkeypatch.setattr(word_conversion, 'available_converters', lambda: [('libreoffice', convert)])
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: None)
    window = _window(qtbot, tmp_path)
    tab = window.open_folder(root)
    tab.search_scope = 'word'
    tab.pattern_edit.setText('needle')
    tab._start_search()
    qtbot.waitUntil(lambda: tab.worker is None, timeout=10000)
    if outcome == 'miss':
        assert not tab.documents and not tab.file_list.topLevelItemCount()
    else:
        assert tab.file_list.topLevelItemCount() == 1
        assert 'failed' in tab.file_list.topLevelItem(0).text(1).lower()
        assert 'failure' in tab.preview.waiting_label.text()
        assert tab.preview.busy_indicator.isHidden()


def test_close_queued_tab_cancels_only_its_work(qtbot, tmp_path, monkeypatch):
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir()
    b.mkdir()
    _docx(a / 'first.docx')
    _docx(b / 'second.docx')
    entered, release = Event(), Event()
    calls = []

    def convert(source, target, cancel):
        calls.append(source.name)
        if source.name == 'first.docx':
            entered.set()
            assert release.wait(15)
        _pdf(target)

    monkeypatch.setattr(word_conversion, '_cache_root', lambda: tmp_path / 'cache')
    monkeypatch.setattr(word_conversion, 'available_converters', lambda: [('libreoffice', convert)])
    window = _window(qtbot, tmp_path)
    try:
        first = window.open_folder(a)
        first.pattern_edit.setText('needle')
        first.search_scope = 'word'
        first._start_search()
        qtbot.waitUntil(entered.is_set)
        second = window.open_folder(b)
        second._start_search()
        qtbot.waitUntil(lambda: window.conversions.state(b / 'second.docx')[0] == 'queued')
        monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
        window.close_tab(window.tabs.indexOf(second))
        assert second in window._pages
        monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
        window.close_tab(window.tabs.indexOf(second))
        qtbot.waitUntil(lambda: second not in window._pages)
        assert first.worker is not None and calls == ['first.docx']
        assert not first.cache_button.isEnabled()
        release.set()
        qtbot.waitUntil(lambda: first.worker is None, timeout=10000)
        assert calls == ['first.docx']
    finally:
        release.set()
        window.close()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=15000)


def test_switch_preserves_results_preview_and_stale_worker_is_ignored(qtbot, tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir()
    b.mkdir()
    path = a / 'pages.pdf'
    with fitz.open() as doc:
        for _ in range(3):
            doc.new_page().insert_text((72, 72), 'needle')
        doc.save(path)
    window = _window(qtbot, tmp_path)
    first = window.open_folder(a)
    first.pattern_edit.setText('needle')
    first._start_search()
    owner = first.worker
    qtbot.waitUntil(lambda: first.worker is None and first.preview._page_count == 3, timeout=10000)
    first.preview.next_button.click()
    qtbot.waitUntil(lambda: not first.preview._workers)
    first.preview.zoom_in_button.click()
    qtbot.waitUntil(lambda: not first.preview._workers)
    zoom = first.preview._zoom
    second = window.open_folder(b)
    window.tabs.setCurrentWidget(first)
    assert first.preview._page_index == 1 and first.preview._zoom == zoom
    assert len(first.documents[0].matches) == 3 and not second.documents
    owner.signals.preliminary.emit(PreliminaryDocument(a / 'old.docx', a / 'old.docx', ()))
    qtbot.wait(30)
    assert len(first.documents) == 1
