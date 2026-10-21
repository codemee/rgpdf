from pathlib import Path
from threading import Event, Thread

import pymupdf as fitz
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QLineEdit

from rgpdf.main_window import MainWindow
from rgpdf.models import SearchOptions
from rgpdf.pdf_passwords import PdfPasswords
from rgpdf.search import search_folder
from rgpdf.worker import SearchWorker
from rgpdf.word_conversion import ConversionCancelled


def _encrypted(path, user='open-secret', owner='owner-secret'):
    with fitz.open() as document:
        for text in ('needle on first page', 'needle on second page'):
            document.new_page().insert_text((72, 72), text)
        document.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=user, owner_pw=owner)
    return path


@pytest.mark.parametrize('isolated', [False, True])
@pytest.mark.parametrize('password', ['open-secret', 'owner-secret'])
def test_password_retry_search_streaming_and_no_secret_in_results(tmp_path, isolated, password):
    path = _encrypted(tmp_path / 'locked.pdf')
    original = path.read_bytes()
    attempts, accepted, streamed = [], [], []
    answers = iter(('wrong-secret', password))

    def request(source, incorrect):
        attempts.append((source, incorrect))
        return next(answers)

    report = search_folder(
        SearchOptions(tmp_path, 'needle'), isolate_pdf_search=isolated,
        password_requested=request, password_accepted=lambda *args: accepted.append(args),
        match_found=lambda *args: streamed.append(args[-1]),
    )
    assert not report.warnings and report.scanned_files == 1
    assert attempts == [(path, False), (path, True)]
    assert accepted == [(path, password)]
    assert len(streamed) == 2 and all(match.highlights for match in streamed)
    assert password not in repr(report) and 'wrong-secret' not in repr(report)
    assert path.read_bytes() == original and list(tmp_path.iterdir()) == [path]
    with fitz.open(path) as document:
        assert document.needs_pass


@pytest.mark.parametrize('isolated', [False, True])
def test_skipping_locked_pdf_continues_with_other_files(tmp_path, isolated):
    locked = _encrypted(tmp_path / 'a.pdf')
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), 'needle')
        document.save(tmp_path / 'b.pdf')
    report = search_folder(SearchOptions(tmp_path, 'needle'), isolate_pdf_search=isolated,
                           password_requested=lambda path, incorrect: None)
    assert report.scanned_files == 2 and len(report.warnings) == 1
    assert report.warnings[0].path == locked
    assert [doc.path.name for doc in report.documents] == ['b.pdf']


def test_session_cache_invalidates_changed_sources_and_clears_on_close(tmp_path):
    path = tmp_path / 'locked.pdf'
    path.write_bytes(b'original')
    passwords = PdfPasswords()
    passwords.remember(path, 'first')
    assert passwords.get(path) == 'first'
    path.write_bytes(b'changed source')
    assert passwords.get(path) is None
    passwords.remember(path, 'second')
    passwords.forget(path)
    assert passwords.get(path) is None
    passwords.remember(path, 'third')
    passwords.close()
    passwords.remember(path, 'late callback')
    assert passwords.get(path) is None


def test_pdf_without_open_password_does_not_prompt(tmp_path):
    _encrypted(tmp_path / 'public.pdf', user='')

    def forbidden(*args):
        raise AssertionError('No opening password is required')

    report = search_folder(SearchOptions(tmp_path, 'needle'), isolate_pdf_search=True,
                           password_requested=forbidden)
    assert not report.warnings and len(report.documents[0].matches) == 2


def test_worker_cancellation_does_not_wait_for_password_dialog(qtbot, tmp_path):
    path = _encrypted(tmp_path / 'locked.pdf')
    worker = SearchWorker(SearchOptions(tmp_path, 'needle'))
    requests, failures = [], []
    worker.signals.password_required.connect(requests.append)

    def wait():
        try:
            worker._request_password(path, False)
        except ConversionCancelled as exc:
            failures.append(exc)

    thread = Thread(target=wait)
    thread.start()
    try:
        qtbot.waitUntil(lambda: bool(requests))
        worker.cancel()
        thread.join(2)
        assert not thread.is_alive() and failures
    finally:
        worker.cancel()
        thread.join(2)


def test_ui_password_retry_preview_navigation_and_reuse(qtbot, tmp_path):
    path = _encrypted(tmp_path / 'locked.pdf')
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    settings.setValue('appearance/language', 'en')
    window = MainWindow(lambda theme: None, settings=settings)
    qtbot.addWidget(window)
    window.folder_edit.setText(str(tmp_path))
    window.pattern_edit.setText('needle')
    window.show()
    window._start_search()
    qtbot.waitUntil(lambda: window._password_dialog is not None, timeout=10000)
    dialog = window._password_dialog
    assert dialog.textEchoMode() == QLineEdit.EchoMode.Password
    dialog.setTextValue('wrong-secret')
    dialog.accept()
    qtbot.waitUntil(lambda: window._password_dialog is not None and window._password_dialog is not dialog,
                    timeout=5000)
    assert 'incorrect' in window._password_dialog.labelText()
    window._password_dialog.setTextValue('open-secret')
    window._password_dialog.accept()
    qtbot.waitUntil(lambda: window.worker is None and window.preview._page_count == 2, timeout=10000)
    assert len(window.documents) == 1 and len(window.documents[0].matches) == 2
    window.preview.next_button.click()
    qtbot.waitUntil(lambda: not window.preview._workers, timeout=5000)
    assert window.preview._page_index == 1
    assert window.preview.image_label.pixmap() and not window.preview.image_label.pixmap().isNull()
    window.preview.fit_page_button.click()
    qtbot.waitUntil(lambda: not window.preview._workers, timeout=5000)
    assert window._pdf_passwords.get(path) == 'open-secret'
    window._start_search()
    qtbot.waitUntil(lambda: window.worker is None, timeout=10000)
    assert window._password_dialog is None and len(window.documents) == 1
    settings.sync()
    assert 'open-secret' not in Path(settings.fileName()).read_text(encoding='utf-8')
    window.close()
    qtbot.waitUntil(lambda: not window.preview._workers, timeout=5000)
    assert window._pdf_passwords.get(path) is None


@pytest.mark.parametrize('action', ['skip', 'cancel', 'close'])
def test_ui_skip_cancel_or_close_during_password_prompt(qtbot, tmp_path, monkeypatch, action):
    _encrypted(tmp_path / 'locked.pdf')
    warnings = []
    monkeypatch.setattr('rgpdf.main_window.QMessageBox.warning', lambda *args: warnings.append(args))
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    window = MainWindow(lambda theme: None, settings=settings)
    qtbot.addWidget(window)
    window.folder_edit.setText(str(tmp_path))
    window.pattern_edit.setText('needle')
    window.show()
    window._start_search()
    qtbot.waitUntil(lambda: window._password_dialog is not None, timeout=10000)
    if action == 'skip':
        window._password_dialog.reject()
    elif action == 'cancel':
        window._cancel_search()
    else:
        window.close()
    qtbot.waitUntil(lambda: window.worker is None, timeout=10000)
    assert window._password_dialog is None and not window.documents
    assert bool(warnings) == (action == 'skip')
    window.close()
