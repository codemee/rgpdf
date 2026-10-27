from threading import Event

import pytest
from PySide6.QtCore import QSettings, Qt

from rgpdf.export_dialog import WordExportDialog
from rgpdf.main_window import MainWindow
from rgpdf import word_conversion, word_export


@pytest.fixture
def conversion(monkeypatch, tmp_path):
    cache = tmp_path / 'cache'
    calls = []

    def convert(source, destination, cancel):
        calls.append(source)
        destination.write_bytes(b'%PDF-test-' + source.name.encode())

    monkeypatch.setattr(word_conversion, '_cache_root', lambda: cache)
    monkeypatch.setattr(word_conversion, 'available_converters', lambda: [('libreoffice', convert)])
    return cache, calls


def test_reuses_any_cached_pdf_and_populates_missing_cache(tmp_path, conversion, monkeypatch):
    cache, calls = conversion
    source = tmp_path / 'chapter.docx'
    other = tmp_path / 'other.doc'
    source.write_bytes(b'word')
    other.write_bytes(b'word')
    cache.mkdir()
    existing = word_conversion._cache_path(source, 'microsoft-word', cache)
    existing.write_bytes(b'%PDF-cached')
    output = tmp_path / 'output'
    output.mkdir()
    report = word_export.export_word_files([source, other], output)
    assert report.exported == 2 and not report.errors
    assert calls == [other]
    assert (output / 'chapter.pdf').read_bytes() == existing.read_bytes()
    assert (output / 'other.pdf').read_bytes() == word_conversion.cached_word_pdf(other).read_bytes()
    # No installed converter is needed when every selected file has a cache.
    monkeypatch.setattr(word_conversion, 'available_converters', lambda: [])
    output2 = tmp_path / 'output2'
    output2.mkdir()
    assert word_export.export_word_files([source, other], output2).exported == 2
    assert source.read_bytes() == b'word'
    source.write_bytes(b'changed-word')
    assert word_conversion.cached_word_pdf(source) is None


def test_existing_targets_and_duplicate_stems(tmp_path, conversion):
    _, calls = conversion
    source = tmp_path / 'same.docx'
    source.write_bytes(b'word')
    output = tmp_path / 'out'
    output.mkdir()
    target = output / 'same.pdf'
    target.write_bytes(b'original')
    report = word_export.export_word_files([source], output)
    assert report.skipped == 1 and not calls
    assert target.read_bytes() == b'original'
    report = word_export.export_word_files([source], output, overwrite=True)
    assert report.exported == 1
    assert target.read_bytes().startswith(b'%PDF-test')
    with pytest.raises(ValueError):
        word_export.export_word_files([source, tmp_path / 'SAME.doc'], output)
    assert not list(output.glob('.rgpdf-*'))


def test_failures_continue_and_cancellation(tmp_path, conversion, monkeypatch):
    _, calls = conversion
    bad, good = tmp_path / 'bad.docx', tmp_path / 'good.docx'
    good.write_bytes(b'word')
    output = tmp_path / 'out'
    output.mkdir()
    report = word_export.export_word_files([bad, good], output)
    assert report.exported == 1 and report.errors[0][0] == bad
    cancel = Event()
    cancel.set()
    assert word_export.export_word_files([good], output, cancel_event=cancel).cancelled
    assert len(calls) == 1
    cancel.clear()
    monkeypatch.setattr(word_export, 'cached_word_pdf', lambda _: (cancel.set(), output / 'good.pdf')[1])
    output2 = tmp_path / 'out2'
    output2.mkdir()
    report = word_export.export_word_files([good], output2, cancel_event=cancel)
    assert report.cancelled and not list(output2.iterdir())


def test_scan_filters_and_export_availability(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    window = MainWindow(lambda _: None, settings=settings)
    qtbot.addWidget(window)
    window.show()
    root = tmp_path / 'docs'
    root.mkdir()
    window._set_folder(root)
    qtbot.waitUntil(lambda: not window._word_scan_timer.isActive() and not window._word_scans)
    assert not window.export_word_button.isEnabled()
    (root / 'ch01.docx').touch()
    (root / 'ch1.doc').touch()
    (root / '~$ch01.docx').touch()
    sub = root / 'sub'
    sub.mkdir()
    (sub / 'ch02.DOCX').touch()
    (root / 'ch03.pdf').touch()
    window.stem_filter_edit.setText('ch0*')
    qtbot.waitUntil(lambda: window.export_word_button.isEnabled())
    assert [p.name for p in window._export_paths] == ['ch01.docx', 'ch02.DOCX']
    window.recursive_button.setChecked(False)
    qtbot.waitUntil(lambda: window.export_word_button.isEnabled())
    assert [p.name for p in window._export_paths] == ['ch01.docx']
    window._set_searching(True)
    assert not window.export_word_button.isEnabled()
    window._set_searching(False)
    assert window.export_word_button.isEnabled()
    # A stale directory result must not restore the previous folder's files.
    window.stem_filter_edit.setText('missing*')
    window._export_files_scanned(window._word_scan_request - 1, [root / 'ch01.docx'])
    assert not window.export_word_button.isEnabled()
    qtbot.waitUntil(lambda: not window._word_scan_timer.isActive() and not window._word_scans)
    assert not window._export_paths


def test_selection_destination_and_collision_validation(qtbot, tmp_path, monkeypatch):
    paths = [tmp_path / 'one.doc', tmp_path / 'one.docx', tmp_path / 'two.docx']
    dialog = WordExportDialog(tmp_path, paths, str(tmp_path), 'en')
    qtbot.addWidget(dialog)
    warnings = []
    monkeypatch.setattr('rgpdf.export_dialog.QMessageBox.warning', lambda *args: warnings.append(args))
    assert not dialog.overwrite.isChecked()
    dialog.accept()
    assert warnings and dialog.result() != dialog.DialogCode.Accepted
    dialog.select_all.setChecked(False)
    assert not dialog.selected_paths() and not dialog.export_button.isEnabled()
    dialog.files.topLevelItem(1).setCheckState(0, Qt.CheckState.Checked)
    assert dialog.selected_paths() == [paths[1]]
    dialog.destination.setText(str(tmp_path / 'missing'))
    dialog.accept()
    assert len(warnings) == 2
    dialog.destination.setText(str(tmp_path))
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted


def test_export_from_main_window(qtbot, tmp_path, conversion, monkeypatch):
    source = tmp_path / 'document.docx'
    source.write_bytes(b'word')
    output = tmp_path / 'out'
    output.mkdir()
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    settings.setValue('appearance/language', 'en')
    settings.setValue('export/folder', str(output))
    window = MainWindow(lambda _: None, settings=settings)
    qtbot.addWidget(window)
    window._set_folder(tmp_path)
    qtbot.waitUntil(lambda: window.export_word_button.isEnabled())
    monkeypatch.setattr(WordExportDialog, 'exec', lambda self: self.DialogCode.Accepted)
    window.export_word_button.click()
    assert window.export_worker is not None
    assert not window.search_button.isEnabled()
    assert not window.export_word_button.isEnabled()
    qtbot.waitUntil(lambda: window.export_worker is None)
    assert (output / 'document.pdf').read_bytes().startswith(b'%PDF-test')
    assert '1 exported' in window.status_label.text()
    assert window.search_button.isEnabled()
    assert window.settings.value('export/folder') == str(output)
