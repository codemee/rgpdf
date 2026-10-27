from PySide6.QtCore import QMimeData, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication
import pytest

from rgpdf.main_window import MainWindow
from rgpdf.models import SearchOptions
from rgpdf.worker import SearchWorker


def _window(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / 'layout.ini'), QSettings.Format.IniFormat)
    settings.setValue('appearance/language', 'en')
    window = MainWindow(lambda theme: None, settings=settings)
    qtbot.addWidget(window)
    window.resize(1100, 750)
    window.show()
    return window


def _drop(window, mime, actions=Qt.DropAction.CopyAction):
    enter = QDragEnterEvent(QPoint(40, 100), actions, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(window, enter)
    drop = QDropEvent(QPointF(40, 100), actions, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(window, drop)
    return enter, drop


@pytest.mark.parametrize('file', [False, True])
def test_drop_uses_folder_or_file_parent_and_persists_without_search(qtbot, tmp_path, file):
    folder = tmp_path / '文件 空白'
    folder.mkdir()
    source = folder / 'report.docx'
    source.write_bytes(b'original document')
    target = source if file else folder
    window = _window(qtbot, tmp_path)
    window.stem_filter_edit.setText('ch0*')
    window.pattern_edit.setText('needle')
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(target))])
    enter, drop = _drop(window, mime)
    assert enter.isAccepted() and drop.isAccepted()
    assert drop.dropAction() == Qt.DropAction.CopyAction
    assert window.folder_edit.text() == str(folder.resolve())
    assert window.settings.value('search/folder') == str(folder.resolve())
    assert window.worker is None and window.stem_filter_edit.text() == 'ch0*'
    assert window.pattern_edit.text() == 'needle'
    assert source.read_bytes() == b'original document'
    assert not any(field.acceptDrops() for field in (
        window.folder_edit, window.stem_filter_edit, window.pattern_edit,
    ))
    window.close()


@pytest.mark.parametrize('kind', ['remote', 'missing', 'text', 'searching', 'move'])
def test_invalid_or_inflight_drops_do_not_change_target(qtbot, tmp_path, kind):
    window = _window(qtbot, tmp_path)
    window._set_folder(tmp_path)
    other = tmp_path / 'other'
    other.mkdir()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(other))])
    if kind == 'remote':
        mime.setUrls([QUrl('https://example.com/document.pdf')])
    elif kind == 'missing':
        mime.setUrls([QUrl.fromLocalFile(str(tmp_path / 'missing.pdf'))])
    elif kind == 'text':
        mime = QMimeData()
        mime.setText(str(other))
    elif kind == 'searching':
        window.worker = SearchWorker(SearchOptions(tmp_path, 'needle'))
    actions = Qt.DropAction.MoveAction if kind == 'move' else Qt.DropAction.CopyAction
    enter, drop = _drop(window, mime, actions)
    assert not enter.isAccepted() and not drop.isAccepted()
    assert window.folder_edit.text() == str(tmp_path)
    assert other.is_dir()
    window.close()


def test_multi_drop_uses_first_valid_local_item(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    mime = QMimeData()
    mime.setUrls([QUrl('https://example.com/a.pdf'),
                  QUrl.fromLocalFile(str(first)), QUrl.fromLocalFile(str(second))])
    enter, drop = _drop(window, mime)
    assert drop.isAccepted() and window.folder_edit.text() == str(first.resolve())
    window.close()


def test_target_title_statusbar_and_right_toolbar_group(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    QApplication.processEvents()
    assert window.search_area.title() == 'Search target'
    assert window.statusBar().isAncestorOf(window.status_label)
    assert window.statusBar().isAncestorOf(window.progress_bar)
    assert not window.left_panel.isAncestorOf(window.status_label)
    assert not window.status_label.wordWrap()
    assert window.settings_toolbar.height() == 42
    assert window.toolbar_spacer.width() > 100
    assert window.cache_button.geometry().right() < window.about_button.x()
    assert window.about_button.x() < window.language_button.x() < window.theme_button.x()
    assert window.settings_toolbar.width() - window.theme_button.geometry().right() <= 12
    window.progress_bar.setRange(0, 100)
    window.progress_bar.setValue(75)
    window.progress_bar.show()
    QApplication.processEvents()
    assert window.progress_bar.width() >= 240
    assert window.progress_bar.width() >= window.statusBar().width() * 0.35
    assert window.status_label.width() > window.progress_bar.width()
    window._set_status('Long status ' * 100)
    assert window.status_label.toolTip() == 'Long status ' * 100
    window.resize(900, 650)
    # Native resize / DPI events may arrive after processEvents returns.
    qtbot.waitUntil(lambda: window.width() <= 900, timeout=5000)
    assert window.progress_bar.width() >= 240
    assert window.settings_toolbar.width() - window.theme_button.geometry().right() <= 12
    window.language = 'zh_TW'
    window.retranslate_ui()
    assert window.search_area.title() == '搜尋標的'
    window.close()
