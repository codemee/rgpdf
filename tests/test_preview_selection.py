from pathlib import Path
import sys

import pymupdf as fitz
import pytest
from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QContextMenuEvent, QImage, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from rgpdf.models import TextMatch
from rgpdf.pdf_passwords import PdfPasswords
from rgpdf.preview import PdfPreview


@pytest.fixture(autouse=True)
def clipboard(monkeypatch):
    """Keep deterministic UI tests from competing with the desktop clipboard."""
    class Clipboard:
        def __init__(self):
            self.value = ''
            self.busy = 0
            self.attempts = 0
            self.owner = False
            self.mime = None

        def setMimeData(self, mime):
            self.attempts += 1
            if self.busy:
                self.busy -= 1
                self.owner = False
            else:
                self.mime, self.owner = mime, True

        def setText(self, text):
            self.attempts += 1
            if self.busy:
                self.busy -= 1
                self.owner = False
            else:
                self.value, self.owner = text, True

        def text(self):
            return self.value

        def ownsClipboard(self):
            return self.owner

    value = Clipboard()
    monkeypatch.setattr(QApplication, 'clipboard', lambda: value)
    return value


def _pdf(path, *, rotation=0, encrypted=False):
    with fitz.open() as document:
        page = document.new_page(width=300, height=240)
        page.insert_text((40, 60), 'Hello world', fontsize=14)
        page.insert_text((40, 85), 'Second line', fontsize=14)
        page.insert_text((40, 115), '循環緩衝區', fontname='china-t', fontsize=14)
        page.set_rotation(rotation)
        document.new_page(width=300, height=240)
        kwargs = dict(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw='secret', owner_pw='owner') if encrypted else {}
        document.save(path, **kwargs)
    return path


def _match():
    return TextMatch('Hello', 'Hello world', 0, 5, 0, 0, ())


def _preview(qtbot, path, passwords=None):
    preview = PdfPreview(passwords=passwords)
    qtbot.addWidget(preview)
    preview.resize(650, 620)
    preview.show()
    preview.show_match(str(path), _match())
    qtbot.waitUntil(lambda: not preview._workers and preview.image_label.has_text(), timeout=5000)
    preview.fit_page_button.click()
    qtbot.waitUntil(lambda: not preview._workers and not preview._resize_timer.isActive(), timeout=5000)
    return preview


@pytest.mark.parametrize('encrypted', [False, True])
def test_copy_whole_page_png(qtbot, tmp_path, clipboard, encrypted):
    path = _pdf(tmp_path / 'page.pdf', encrypted=encrypted)
    passwords = PdfPasswords()
    if encrypted:
        passwords.remember(path, 'secret')
    preview = _preview(qtbot, path, passwords)
    assert len(preview.toolbar_separators) == 2
    preview._change_zoom(2)
    assert not preview.copy_page_button.isEnabled()
    qtbot.waitUntil(lambda: not preview._workers)
    image = preview.image_label.pixmap().toImage()
    assert image.height() > preview.scroll_area.viewport().height()
    clipboard.busy = 2 if sys.platform == 'win32' else 0
    preview.copy_page_button.click()
    qtbot.waitUntil(lambda: preview._pending_png is None)
    assert clipboard.mime.hasImage()
    png = clipboard.mime.data('image/png')
    assert bytes(png).startswith(b'\x89PNG\r\n\x1a\n')
    assert QImage.fromData(png, 'PNG') == image
    assert clipboard.mime.imageData() == image
    preview.next_button.click()
    assert not preview.copy_page_button.isEnabled()
    qtbot.waitUntil(lambda: not preview._workers)
    assert not preview.image_label.has_text()
    assert preview.copy_page_button.isEnabled()
    preview.copy_page_button.click()
    blank = QImage.fromData(clipboard.mime.data('image/png'), 'PNG')
    assert blank == preview.image_label.pixmap().toImage()
    assert blank != image
    preview.clear()
    assert not preview.copy_page_button.isEnabled()
    old_mime = clipboard.mime
    preview._copy_page()
    assert clipboard.mime is old_mime


def _position(label, offset, *, after):
    data = label._page_text
    glyph_index, glyph = next((i, g) for i, g in enumerate(data.glyphs)
                              if (g.end if after else g.start) == offset)
    line = next(line for line in data.lines if line.start <= glyph_index < line.end)
    dx, dy = line.direction
    length = (dx * dx + dy * dy) ** 0.5
    dx, dy = dx / length, dy / length
    x0, y0, x1, y1 = glyph.rectangle
    distance = (abs(dx) * (x1 - x0) + abs(dy) * (y1 - y0)) * (0.4 if after else -0.4)
    point = QPointF((x0 + x1) / 2 + dx * distance, (y0 + y1) / 2 + dy * distance)
    return (point * label._zoom + label._image_origin()).toPoint()


def _drag(qtbot, preview, phrase, reverse=False, before_release=None):
    label = preview.image_label
    qtbot.waitUntil(lambda: label.has_text() and not preview._workers
                    and not preview._resize_timer.isActive(), timeout=5000)
    start = label._page_text.text.index(phrase)
    begin, end = _position(label, start, after=False), _position(label, start + len(phrase), after=True)
    if reverse:
        begin, end = end, begin
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=begin)
    qtbot.mouseMove(label, end, delay=10)
    if before_release is not None:
        before_release()
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=end)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('reverse', [False, True])
def test_drag_copy_and_shortcut_match_displayed_text(qtbot, tmp_path, rotation, reverse):
    path = _pdf(tmp_path / 'selection.pdf', rotation=rotation)
    preview = _preview(qtbot, path)
    clipboard = QApplication.clipboard()
    clipboard.setText('unchanged while dragging')
    assert preview.select_text_button.isChecked()
    def during_drag():
        assert clipboard.text() == 'unchanged while dragging'

    _drag(qtbot, preview, 'Hello world', reverse, before_release=during_drag)
    assert preview.image_label.selected_text() == 'Hello world'
    qtbot.waitUntil(lambda: clipboard.text() == 'Hello world', timeout=3000)
    _drag(qtbot, preview, '緩衝', reverse)
    assert preview.image_label.selected_text() == '緩衝'
    clipboard.setText('verify shortcut copy')
    QTest.keySequence(preview.image_label, QKeySequence(QKeySequence.StandardKey.Copy))
    qtbot.waitUntil(lambda: clipboard.text() == '緩衝', timeout=3000)
    preview.close()


def test_multiline_selection_and_zoom_keep_clipboard_text_correct(qtbot, tmp_path):
    preview = _preview(qtbot, _pdf(tmp_path / 'selection.pdf'))
    data = preview.image_label._page_text.text
    phrase = data[data.index('world'):data.index('Second') + len('Second')]
    _drag(qtbot, preview, phrase)
    assert QApplication.clipboard().text().replace('\n\n', '\n') == 'world\nSecond'
    preview.zoom_in_button.click()
    assert not preview.image_label.selected_text()
    qtbot.waitUntil(lambda: not preview._workers, timeout=5000)
    _drag(qtbot, preview, 'Hello')
    assert QApplication.clipboard().text() == 'Hello'
    preview.close()


def test_selection_mode_keyboard_and_page_changes_clear_selection(qtbot, tmp_path):
    preview = _preview(qtbot, _pdf(tmp_path / 'selection.pdf'))
    label = preview.image_label
    QTest.keySequence(label, QKeySequence(QKeySequence.StandardKey.SelectAll))
    assert 'Hello world' in label.selected_text() and '循環緩衝區' in label.selected_text()
    copied = QApplication.clipboard().text()
    assert copied == label.selected_text()
    qtbot.keyClick(label, Qt.Key.Key_Escape)
    assert not label.selected_text()
    assert QApplication.clipboard().text() == copied
    preview.select_text_button.click()
    _drag(qtbot, preview, 'Hello')
    assert not label.selected_text()
    assert QApplication.clipboard().text() == copied
    preview.select_text_button.click()
    _drag(qtbot, preview, 'Hello')
    assert QApplication.clipboard().text() == 'Hello'
    preview.next_button.click()
    assert not label.selected_text()
    qtbot.waitUntil(lambda: not preview._workers, timeout=5000)
    assert not label.has_text() and not preview.select_text_button.isEnabled()
    assert 'no selectable text' in preview.select_text_button.toolTip()
    preview.previous_button.click()
    qtbot.waitUntil(lambda: not preview._workers, timeout=5000)
    assert label.has_text() and not label.selected_text()
    old_request, old_text, image, zoom = preview._request_id, label._page_text, label.pixmap().toImage(), preview._zoom
    preview.clear()
    preview._render_finished(old_request, image, 2, zoom, old_text)
    assert not label.has_text() and not label.selected_text()
    preview.close()


def test_authenticated_pdf_selection_does_not_modify_source(qtbot, tmp_path):
    path = _pdf(tmp_path / 'encrypted.pdf', encrypted=True)
    original = path.read_bytes()
    passwords = PdfPasswords()
    passwords.remember(path, 'secret')
    preview = _preview(qtbot, path, passwords)
    _drag(qtbot, preview, 'world')
    assert QApplication.clipboard().text() == 'world'
    assert path.read_bytes() == original
    preview.close()


def test_busy_clipboard_retries_and_clear_cancels_pending_copy(qtbot, tmp_path, clipboard):
    preview = _preview(qtbot, _pdf(tmp_path / 'selection.pdf'))
    clipboard.busy = 2
    _drag(qtbot, preview, 'Hello')
    qtbot.waitUntil(lambda: clipboard.text() == 'Hello', timeout=3000)
    assert clipboard.attempts == 3
    clipboard.busy = 10
    _drag(qtbot, preview, 'world')
    attempts = clipboard.attempts
    preview.clear()
    qtbot.wait(200)
    assert clipboard.attempts == attempts and clipboard.text() == 'Hello'
    preview.close()


def test_context_menu_copies_selection(qtbot, tmp_path):
    preview = _preview(qtbot, _pdf(tmp_path / 'selection.pdf'))
    _drag(qtbot, preview, 'world')
    label = preview.image_label
    QApplication.clipboard().setText('replace this with the selected text')
    position = label.rect().center()

    def choose_copy():
        menu = QApplication.activePopupWidget()
        assert menu is not None
        assert menu.actions()[0].text() == 'Copy selected text'
        menu.actions()[0].trigger()
        menu.close()

    QTimer.singleShot(0, choose_copy)
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, position, label.mapToGlobal(position))
    QApplication.sendEvent(label, event)
    qtbot.waitUntil(lambda: QApplication.clipboard().text() == 'world', timeout=3000)
    preview.close()
