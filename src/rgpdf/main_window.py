# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
import os

from PySide6.QtCore import QEvent, QLocale, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QTabBar, QTabWidget, QVBoxLayout, QWidget

from rgpdf import __version__
from rgpdf.buttons import SettingsButton
from rgpdf.conversion_service import WordConversionService
from rgpdf.folder_session import FolderSettings, FolderTabState, TAB_DEFAULTS
from rgpdf.folder_tab import FolderTab
from rgpdf.i18n import translate
from rgpdf.main_window_toolbar import FolderTabBar, SettingsToolBar
from rgpdf.pdf_passwords import PdfPasswords
from rgpdf.resources import application_icon
from rgpdf.word_conversion import clear_word_cache


class MainWindow(QMainWindow):
    LANGUAGE_CYCLE = ('system', 'zh_TW', 'en')
    THEME_CYCLE = ('system', 'light', 'dark')

    def __init__(self, apply_theme_callback, settings=None):
        super().__init__()
        self.settings = settings or QSettings('rgpdf', 'rgpdf')
        self.apply_theme_callback = apply_theme_callback
        self._pages = []
        self._pending_close = set()
        self._shown = None
        self._closing = False
        self._pdf_passwords = PdfPasswords()
        self.conversions = WordConversionService(self)
        self.language_preference = self.settings.value('appearance/language', 'system', type=str)
        if self.language_preference not in self.LANGUAGE_CYCLE:
            self.language_preference = 'system'
        self.language = self._resolved_language(self.language_preference)
        self.theme_preference = self.settings.value('appearance/theme', 'system', type=str)
        if self.theme_preference not in self.THEME_CYCLE:
            self.theme_preference = 'system'
        self.highlight_color = QColor(self.settings.value('appearance/highlight_color', '#ffe128', type=str))
        self.setWindowIcon(application_icon())
        self.setAcceptDrops(True)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('folderTabs')
        self.tabs.setTabBar(FolderTabBar())
        self.tabs.tabBar().setObjectName('folderTabBar')
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(False)
        central = QWidget()
        central.setObjectName('centralWidget')
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(12, 0, 12, 8)
        central_layout.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.add_folder_button = SettingsButton('add_folder')
        self.add_folder_button.clicked.connect(self.choose_folder)
        # QTabWidget reserves sizeHint(), whereas the painted button uses a
        # larger fixed footprint. A layout exposes that complete footprint.
        corner = QWidget()
        corner.setFixedSize(SettingsButton.BUTTON_SIZE, SettingsButton.BUTTON_SIZE)
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.addWidget(self.add_folder_button)
        self.tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)
        self.tabs.currentChanged.connect(self._switch_tab)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabBar().tabMoved.connect(lambda *_: self._save_session())
        self.background_label = QLabel()
        self.statusBar().addPermanentWidget(self.background_label)
        self.about_action = QAction(self)
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        self.about_action.triggered.connect(self._show_about)
        self._system_menu = None
        import sys
        if sys.platform == 'win32':
            from rgpdf.system_menu import WindowsSystemMenu
            self._system_menu = WindowsSystemMenu()
        else:
            self.menuBar().addMenu('rgPDF').addAction(self.about_action)
        self._restoring = True
        self._restore_tabs()
        self._restoring = False
        geometry = self.settings.value('window/geometry')
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1280, 780)
        self.retranslate_ui()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

    @property
    def current_tab(self):
        return self.tabs.currentWidget()

    def __getattr__(self, name):
        # Preserve the existing active-folder API for callers during migration.
        tabs = self.__dict__.get('tabs')
        tab = tabs.currentWidget() if tabs is not None else None
        if tab is not None and hasattr(tab, name):
            return getattr(tab, name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in {'worker', 'export_worker', 'search_scope'}:
            tabs = self.__dict__.get('tabs')
            tab = tabs.currentWidget() if tabs is not None else None
            if tab is not None:
                setattr(tab, name, value)
                return
        super().__setattr__(name, value)

    def t(self, key, **values):
        return translate(self.language, key, **values)

    @staticmethod
    def _resolved_language(preference):
        if preference in {'zh_TW', 'en'}:
            return preference
        return 'zh_TW' if QLocale.system().name().lower().startswith('zh') else 'en'

    def _create_tab(self, state=None):
        tab = FolderTab(self, FolderSettings(self.settings, state))
        self._pages.append(tab)
        tab.changed.connect(self._page_changed)
        tab.language = self.language
        tab.language_preference = self.language_preference
        tab.theme_preference = self.theme_preference
        tab.retranslate_ui()
        index = self.tabs.addTab(tab, '')
        close = SettingsButton('close_tab')
        close.setObjectName('folderTabClose')
        close.setFixedSize(20, 20)
        close.setContentsMargins(0, 0, 0, 0)
        close.clicked.connect(lambda: self.tabs.tabCloseRequested.emit(self.tabs.indexOf(tab)))
        self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, close)
        self._refresh_titles()
        return tab

    def _restore_tabs(self):
        current = self.settings.value('session/current_tab', 0, type=int)
        saved = self.settings.contains('session/tabs/size')
        count = self.settings.beginReadArray('session/tabs')
        states = []
        for i in range(count):
            self.settings.setArrayIndex(i)
            values = {key: self.settings.value(key, default) for key, default in TAB_DEFAULTS.items()}
            states.append(FolderTabState(values))
        self.settings.endArray()
        if not saved:
            self._create_tab()
        else:
            for state in states:
                self._create_tab(state)
            if not states:
                values = {key: self.settings.value(key, default) for key, default in TAB_DEFAULTS.items()}
                values.update({'search/folder': '', 'export/folder': ''})
                self._create_tab(FolderTabState(values))
        self.tabs.setCurrentIndex(min(max(0, current), self.tabs.count() - 1))

    def _save_session(self):
        if not self._pages or self.__dict__.get('_restoring', False):
            return
        opened = [self.tabs.widget(i) for i in range(self.tabs.count())
                  if self.tabs.widget(i).folder_edit.text()]
        current = self.current_tab
        self.settings.beginWriteArray('session/tabs', len(opened))
        for i, tab in enumerate(opened):
            self.settings.setArrayIndex(i)
            # Write captured values directly: per-tab snapshots must not write
            # legacy defaults while QSettings is inside an array group.
            values = dict(tab.settings.state.values)
            values.update({'search/pattern': tab.pattern_edit.text(),
                           'search/stem_glob': tab.stem_filter_edit.text(),
                           'window/main_splitter': tab.main_splitter.saveState(),
                           'window/result_splitter': tab.result_splitter.saveState()})
            for key, value in values.items():
                if value is not None:
                    self.settings.setValue(key, value)
        self.settings.endArray()
        self.settings.setValue('session/current_tab', opened.index(current) if current in opened else 0)
        self.settings.sync()

    def choose_folder(self):
        if self._closing:
            return
        start = self.current_tab.folder_edit.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, self.t('choose_folder'), start)
        if folder:
            self.open_folder(Path(folder))

    def open_folder(self, folder):
        if self._closing:
            return None
        folder = Path(folder).resolve()
        identity = os.path.normcase(str(folder))
        for tab in self._pages:
            path = tab.folder_edit.text()
            if path and os.path.normcase(str(Path(path).resolve())) == identity:
                self.tabs.setCurrentWidget(tab)
                return tab
        current = self.current_tab
        if current is not None and not current.folder_edit.text() and not current.is_busy():
            tab = current
        else:
            values = current.snapshot() if current is not None else dict(TAB_DEFAULTS)
            values['search/folder'] = str(folder)
            values['export/folder'] = str(folder)
            tab = self._create_tab(FolderTabState(values))
        tab._set_folder(folder)
        tab.settings.setValue('export/folder', str(folder))
        self.tabs.setCurrentWidget(tab)
        self._save_session()
        return tab

    def _switch_tab(self, index):
        previous = self._shown
        if previous is not None:
            self.removeToolBar(previous.settings_toolbar)
            previous.settings_toolbar.setParent(previous)
            previous.settings_toolbar.hide()
            for widget in (previous.status_label, previous.progress_bar):
                self.statusBar().removeWidget(widget)
                widget.setParent(previous)
                widget.hide()
        tab = self.current_tab
        self._shown = tab
        if tab is None:
            return
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tab.settings_toolbar)
        tab.settings_toolbar.show()
        self.statusBar().addWidget(tab.status_label, 3)
        self.statusBar().addPermanentWidget(tab.progress_bar, 2)
        tab.status_label.show()
        tab.progress_bar.setVisible(tab.is_busy())
        self._refresh_titles()
        if not self._closing:
            self._save_session()

    def _refresh_titles(self):
        paths = [self.tabs.widget(i).folder_edit.text() for i in range(self.tabs.count())]
        for i, text in enumerate(paths):
            tab = self.tabs.widget(i)
            if not text:
                title = self.t('empty_folder_tab')
            else:
                path = Path(text)
                title = path.name or str(path)
                depth = 1
                while any(other and other != text and str(Path(other)).split(os.sep)[-depth:] == str(path).split(os.sep)[-depth:]
                          for other in paths):
                    depth += 1
                if depth > 1:
                    title = os.sep.join(path.parts[-depth:])
            if tab in self._pending_close:
                title += ' · ' + self.t('tab_closing')
            elif tab.is_busy():
                title += ' · ' + self.t('tab_exporting' if tab.export_worker is not None else 'tab_searching')
            if self.tabs.tabText(i) != title:
                self.tabs.setTabText(i, title)
            self.tabs.setTabToolTip(i, text or self.t('empty_folder_tab'))
            for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
                button = self.tabs.tabBar().tabButton(i, side)
                if button is not None:
                    button.setToolTip(self.t('close_folder_tab'))
                    button.setAccessibleName(self.t('close_folder_tab'))

    def _page_changed(self):
        if not self._closing:
            self._refresh_titles()

    def any_busy(self):
        return any(tab.is_busy() for tab in self._pages) or self.conversions.is_busy()

    def close_tab(self, index):
        if self._closing:
            return
        tab = self.tabs.widget(index)
        if tab is None or tab in self._pending_close:
            return
        if tab.is_busy():
            answer = QMessageBox.question(self, self.t('close_folder_tab'), self.t('close_busy_tab'),
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._pending_close.add(tab)
        tab.shutdown()
        self._poll()

    def _remove_tab(self, tab):
        index = self.tabs.indexOf(tab)
        if index >= 0:
            self.tabs.removeTab(index)
        self._pending_close.discard(tab)
        self._pages.remove(tab)
        tab.deleteLater()
        if not self._pages and not self._closing:
            values = {key: self.settings.value(key, default) for key, default in TAB_DEFAULTS.items()}
            values.update({'search/folder': '', 'export/folder': ''})
            self._create_tab(FolderTabState(values))
        self._save_session()

    def _poll(self):
        for tab in list(self._pending_close):
            if tab.settled():
                self._remove_tab(tab)
        if self._closing:
            if all(tab.settled() for tab in self._pages) and self.conversions.is_stopped():
                self.close()
            return
        busy = self.any_busy()
        for tab in self._pages:
            tab.cache_button.setEnabled(not busy)
        count = sum(tab.is_busy() for tab in self._pages if tab is not self.current_tab)
        self.background_label.setText(self.t('background_jobs', count=count) if count else '')
        self._refresh_titles()

    def retranslate_ui(self):
        self.setWindowTitle(self.t('app_title', version=__version__))
        self.add_folder_button.setToolTip(self.t('add_folder_tab'))
        self.about_action.setText(self.t('about_title'))
        if self._system_menu is not None and self.isVisible():
            self._system_menu.update(int(self.winId()), self.about_action.text())
        for tab in self._pages:
            tab.language = self.language
            tab.language_preference = self.language_preference
            tab.theme_preference = self.theme_preference
            tab.retranslate_ui()
        self._refresh_titles()

    def _cycle_language(self):
        self.language_preference = self.LANGUAGE_CYCLE[(self.LANGUAGE_CYCLE.index(self.language_preference) + 1) % 3]
        self.language = self._resolved_language(self.language_preference)
        self.settings.setValue('appearance/language', self.language_preference)
        self.retranslate_ui()

    def _cycle_theme(self):
        self.theme_preference = self.THEME_CYCLE[(self.THEME_CYCLE.index(self.theme_preference) + 1) % 3]
        self.settings.setValue('appearance/theme', self.theme_preference)
        self.apply_theme_callback(self.theme_preference)
        for tab in self._pages:
            tab.theme_preference = self.theme_preference
            tab._refresh_settings_buttons()

    def _set_highlight_color(self, value):
        color = QColor(value)
        if not color.isValid():
            return
        self.highlight_color = color
        self.settings.setValue('appearance/highlight_color', color.name())
        for tab in self._pages:
            tab.highlight_color = color
            tab.preview.set_highlight_color(color.name())
            tab._refresh_highlight_swatches()
            tab.highlight_button.setChecked(False)
            tab._refresh_settings_buttons()

    def _clear_word_cache(self):
        if self._closing or self.any_busy():
            return
        answer = QMessageBox.question(self, self.t('clear_word_cache'), self.t('clear_all_tab_cache'),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        for tab in self._pages:
            tab.preview.clear()
            tab.documents = [doc for doc in tab.documents if doc.path.suffix.casefold() == '.pdf']
            tab._document_indexes = {doc.path: i for i, doc in enumerate(tab.documents)}
            tab._populate_files()
        result = clear_word_cache()
        QMessageBox.information(self, self.t('clear_word_cache'),
            self.t('cache_cleared_body', count=result.removed_files,
                   size=f'{result.removed_bytes / (1024 * 1024):.1f}', failed=result.failed_files))

    def _dropped_folders(self, mime):
        if self._closing or not mime.hasUrls():
            return []
        folders = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            try:
                path = Path(url.toLocalFile())
                folder = path if path.is_dir() else path.parent if path.is_file() else None
                if folder is not None:
                    folders.append(folder.resolve())
            except (OSError, RuntimeError):
                continue
        return folders

    def dragEnterEvent(self, event):
        if event.possibleActions() & Qt.DropAction.CopyAction and self._dropped_folders(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        folders = self._dropped_folders(event.mimeData())
        if not folders or not event.possibleActions() & Qt.DropAction.CopyAction:
            event.ignore()
            return
        for folder in folders:
            self.open_folder(folder)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def _show_about(self):
        QMessageBox.about(self, self.t('about_title'), self.t('about_content', version=__version__))

    def showEvent(self, event):
        super().showEvent(event)
        if self._system_menu is not None:
            self._system_menu.update(int(self.winId()), self.about_action.text())

    def nativeEvent(self, event_type, message):
        menu = getattr(self, '_system_menu', None)
        if menu is not None and event_type == b'windows_generic_MSG' and menu.is_about_message(message):
            QTimer.singleShot(0, self.about_action.trigger)
            return True, 0
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event):
        if not self._closing:
            self._save_session()
            self.settings.setValue('window/geometry', self.saveGeometry())
            self._closing = True
            self.add_folder_button.setEnabled(False)
            for tab in self._pages:
                tab.shutdown()
            self._pdf_passwords.close()
            self.conversions.close()
        if all(tab.settled() for tab in self._pages) and self.conversions.is_stopped():
            self._poll_timer.stop()
            event.accept()
        else:
            event.ignore()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.LocaleChange and self.language_preference == 'system':
            self.language = self._resolved_language('system')
            self.retranslate_ui()
