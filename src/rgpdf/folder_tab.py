# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QLocale, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QHeaderView,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from rgpdf.buttons import SettingsButton
from rgpdf.export_dialog import WordExportDialog
from rgpdf.i18n import translate
from rgpdf.models import DocumentMatch, PreliminaryDocument, PreliminaryMatch, SearchOptions, SearchReport
from rgpdf.main_window_toolbar import SettingsToolBar
from rgpdf.preview import PdfPreview
from rgpdf.progress import SearchProgressBar
from rgpdf.search import SearchInputError, compile_pattern
from rgpdf.worker import SearchWorker, PdfPasswordRequest
from rgpdf.word_export import ExportReport, WordExportWorker, WordFileScanWorker

class FolderTab(QWidget):
    changed = Signal()
    LANGUAGE_CYCLE = ("system", "zh_TW", "en")
    THEME_CYCLE = ("system", "light", "dark")

    def __init__(self, host, settings) -> None:
        super().__init__()
        self.host = host
        self.settings = settings
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(3)
        self._pending_errors = {}
        self._export_progress_state = None
        self.worker: SearchWorker | None = None
        self.export_worker: WordExportWorker | None = None
        self._export_paths: list[Path] = []
        self._word_scan_request = 0
        self._word_scans: dict[int, WordFileScanWorker] = {}
        self._word_scan_timer = QTimer(self)
        self._word_scan_timer.setSingleShot(True)
        self._word_scan_timer.setInterval(150)
        self._word_scan_timer.timeout.connect(self._scan_export_files)
        self._export_watcher = QFileSystemWatcher(self)
        self._export_watcher.directoryChanged.connect(self._queue_word_scan)
        self._pdf_passwords = host._pdf_passwords
        self._password_dialog: QInputDialog | None = None
        self._closing = False
        self._search_progress_state: tuple[int, int, str] | None = None
        self._converting_word_name = ""
        self._screening_state = None
        self._candidate_count = 0
        self.documents: list[DocumentMatch | PreliminaryDocument] = []
        self._document_indexes: dict[Path, int] = {}
        self.language_preference = self._initial_language_preference()
        self.language = self._resolved_language(self.language_preference)
        stored_theme = self.settings.value("appearance/theme", "system", type=str)
        self.theme_preference = stored_theme if stored_theme in self.THEME_CYCLE else "system"
        stored_highlight = self.settings.value(
            "appearance/highlight_color", "#ffe128", type=str
        )
        self.highlight_color = QColor(stored_highlight)
        if not self.highlight_color.isValid():
            self.highlight_color = QColor("#ffe128")

        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setAcceptDrops(False)
        self.browse_button = SettingsButton("browse")
        self.stem_filter_edit = QLineEdit()
        self.stem_filter_edit.setAcceptDrops(False)
        self.stem_filter_edit.setText(
            self.settings.value("search/stem_glob", "", type=str)
        )
        stored_scope = self.settings.value("search/scope", "pdf", type=str)
        if stored_scope not in {"pdf", "word", "all"}:
            stored_scope = "pdf"
        self.search_scope = stored_scope
        self.scope_button = self._settings_button()
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setAcceptDrops(False)
        self.pattern_edit.setText(self.settings.value("search/pattern", "", type=str))
        use_regex = self.settings.value("search/use_regex", True, type=bool)
        self.language_button = self._settings_button()
        self.theme_button = self._settings_button()
        self.regex_button = self._settings_button(checkable=True)
        self.regex_button.setChecked(use_regex)
        self.line_wrap_button = self._settings_button(checkable=True)
        self.line_wrap_button.set_icon_kind("line_wrap")
        self.line_wrap_button.setChecked(
            self.settings.value("search/ignore_line_wraps", False, type=bool)
        )
        self.case_button = self._settings_button(checkable=True)
        self.case_button.setChecked(
            self.settings.value("search/case_sensitive", False, type=bool)
        )
        self.recursive_button = self._settings_button(checkable=True)
        self.recursive_button.setChecked(
            self.settings.value("search/recursive", True, type=bool)
        )
        self.highlight_button = self._settings_button(checkable=True)
        self.cache_button = self._settings_button()
        self.cache_button.set_icon_kind("cache")
        self.export_word_button = SettingsButton("export_pdf")
        self.export_word_button.setEnabled(False)
        self.search_button = SettingsButton("search")
        self.cancel_button = SettingsButton("cancel")
        self.cancel_button.setEnabled(False)
        self.progress_bar = SearchProgressBar()
        self.progress_bar.setVisible(False)
        self.status_label = QLabel()
        self.status_label.setWordWrap(False)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        saved_folder = self.settings.value("search/folder", "", type=str)
        self.folder_edit.setText(saved_folder)

        self.search_form = QFormLayout()
        self.search_form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.setSpacing(SettingsButton.SPACING)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(self.browse_button)
        folder_container = QWidget()
        folder_container.setLayout(folder_row)
        self.folder_label = self._make_label("folder")
        self.search_form.addRow(self.folder_label, folder_container)

        self.stem_filter_label = self._make_label("stem_filter")
        self.stem_filter_label.setBuddy(self.stem_filter_edit)
        self.stem_filter_help_button, self.stem_filter_help_menu, self.stem_filter_help_content = (
            self._make_help_control("stemFilter")
        )
        self.search_form.addRow(
            self.stem_filter_label,
            self._field_with_help(self.stem_filter_edit, self.stem_filter_help_button),
        )

        pattern_row = QHBoxLayout()
        pattern_row.setContentsMargins(0, 0, 0, 0)
        pattern_row.addWidget(self.pattern_edit, 1)
        pattern_row.addWidget(self.search_button)
        pattern_row.addWidget(self.cancel_button)
        pattern_container = QWidget()
        pattern_container.setLayout(pattern_row)
        self.pattern_label = self._make_label("pattern")
        self.pattern_help_button, self.pattern_help_menu, self.pattern_help_content = (
            self._make_help_control("pattern")
        )
        pattern_row.insertWidget(0, self.pattern_help_button)
        pattern_row.setSpacing(SettingsButton.SPACING)
        self.search_form.addRow(self.pattern_label, pattern_container)

        self.search_area = QGroupBox()
        self.search_area.setObjectName("searchArea")
        search_area_layout = QVBoxLayout(self.search_area)
        search_area_layout.setContentsMargins(10, 8, 10, 8)
        search_area_layout.addLayout(self.search_form)

        self.settings_toolbar = SettingsToolBar()
        self.settings_toolbar.setObjectName("settingsToolbar")
        self.settings_toolbar.setMovable(False)
        self.settings_toolbar.setFloatable(False)
        self.settings_toolbar.layout().setSpacing(SettingsButton.SPACING)
        for button in (
            self.recursive_button,
            self.scope_button,
            self.case_button,
            self.regex_button,
            self.line_wrap_button,
        ):
            self.settings_toolbar.addWidget(button)
        self.settings_toolbar.addSeparator()
        for button in (
            self.highlight_button,
            self.cache_button,
            self.export_word_button,
        ):
            self.settings_toolbar.addWidget(button)
        self.toolbar_spacer = QWidget()
        self.toolbar_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.settings_toolbar.addWidget(self.toolbar_spacer)
        self.settings_toolbar.addSeparator()
        for button in (
            self.language_button,
            self.theme_button,
        ):
            self.settings_toolbar.addWidget(button)

        self.highlight_panel = QFrame()
        self.highlight_panel.setObjectName("highlightPanel")
        self.highlight_panel.setVisible(False)
        highlight_layout = QHBoxLayout(self.highlight_panel)
        highlight_layout.setSpacing(SettingsButton.SPACING)
        highlight_layout.setContentsMargins(10, 7, 10, 7)
        self.highlight_panel_label = QLabel()
        highlight_layout.addWidget(self.highlight_panel_label)
        self.highlight_swatches: dict[str, SettingsButton] = {}
        for color in ("#ffe128", "#8ee6a1", "#7dddf2", "#f7a8ca", "#ffb36b"):
            button = SettingsButton()
            button.setFixedSize(28, 28)
            button.setProperty("highlight_swatch", True)
            button.clicked.connect(lambda _checked=False, value=color: self._set_highlight_color(value))
            self.highlight_swatches[color] = button
            highlight_layout.addWidget(button)
        self.custom_color_button = SettingsButton("custom_color")
        self.highlight_color_value = QLabel()
        highlight_layout.addWidget(self.custom_color_button)
        highlight_layout.addWidget(self.highlight_color_value)
        highlight_layout.addStretch()


        self.file_group = QGroupBox()
        self.match_group = QGroupBox()
        self.preview_group = QGroupBox()
        self.file_list = self._result_table()
        self.match_list = self._result_table()
        self.file_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.match_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.match_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.preview = PdfPreview(passwords=self._pdf_passwords)
        self.preview.set_highlight_color(self.highlight_color.name())
        self.file_group.setLayout(self._single_widget_layout(self.file_list))
        self.match_group.setLayout(self._single_widget_layout(self.match_list))
        self.preview_group.setLayout(self._single_widget_layout(self.preview))

        self.result_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.result_splitter.addWidget(self.file_group)
        self.result_splitter.addWidget(self.match_group)
        self.result_splitter.setStretchFactor(0, 2)
        self.result_splitter.setStretchFactor(1, 3)
        self.result_splitter.setHandleWidth(10)
        self.result_splitter.setSizes([250, 370])

        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_layout.addWidget(self.search_area)
        left_layout.addWidget(self.result_splitter, 1)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self.preview_group)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setHandleWidth(12)
        self.main_splitter.setSizes([620, 660])

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 8, 12, 12)
        root_layout.addWidget(self.highlight_panel)
        root_layout.addWidget(self.main_splitter, 1)
        self.setObjectName("folderTab")

        self._connect_signals()
        self._restore_window_state()
        self.retranslate_ui()
        self._queue_word_scan()

        self._pending_timer = QTimer(self)
        self._pending_timer.setInterval(150)
        self._pending_timer.timeout.connect(self._refresh_pending_preview)
        self._pending_timer.start()

    @staticmethod
    def _single_widget_layout(widget: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 8, 6, 6)
        layout.addWidget(widget)
        return layout

    def _make_help_control(self, name: str) -> tuple[SettingsButton, QMenu, QLabel]:
        button = SettingsButton("help")
        button.setObjectName(f"{name}HelpButton")
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self)
        menu.setObjectName(f"{name}HelpMenu")
        content = QLabel()
        content.setObjectName(f"{name}HelpContent")
        content.setTextFormat(Qt.TextFormat.RichText)
        content.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        content.setOpenExternalLinks(True)
        content.setWordWrap(True)
        content.setFixedWidth(390)
        content.setContentsMargins(10, 8, 10, 8)
        action = QWidgetAction(menu)
        action.setDefaultWidget(content)
        menu.addAction(action)
        return button, menu, content

    @staticmethod
    def _field_with_help(field: QWidget, button: SettingsButton) -> QWidget:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SettingsButton.SPACING)
        layout.addWidget(button)
        layout.addWidget(field, 1)
        container = QWidget()
        container.setLayout(layout)
        return container

    @staticmethod
    def _result_table() -> QTreeWidget:
        table = QTreeWidget()
        table.setColumnCount(2)
        # Honor each column's resize mode instead of stretching the final column.
        table.header().setStretchLastSection(False)
        table.setRootIsDecorated(False)
        table.setItemsExpandable(False)
        table.setUniformRowHeights(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        return table

    def _make_label(self, key: str) -> QLabel:
        label = QLabel()
        label.setProperty("translation_key", key)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return label

    @staticmethod
    def _settings_button(*, checkable: bool = False) -> SettingsButton:
        return SettingsButton(checkable=checkable)

    def _initial_language_preference(self) -> str:
        stored = self.settings.value("appearance/language", "system", type=str)
        return stored if stored in {"system", "zh_TW", "en"} else "system"

    @staticmethod
    def _resolved_language(preference: str) -> str:
        if preference in {"zh_TW", "en"}:
            return preference
        return "zh_TW" if QLocale.system().name().lower().startswith("zh") else "en"

    def _connect_signals(self) -> None:
        self.browse_button.clicked.connect(self._choose_folder)
        self.search_button.clicked.connect(self._start_search)
        self.cancel_button.clicked.connect(self._cancel_search)
        self.pattern_edit.returnPressed.connect(self._start_search)
        self.stem_filter_edit.returnPressed.connect(self._start_search)
        self.stem_filter_edit.editingFinished.connect(self._save_stem_filter)
        self.pattern_edit.editingFinished.connect(self._save_pattern)
        self.pattern_help_button.clicked.connect(self._show_pattern_help)
        self.stem_filter_help_button.clicked.connect(self._show_stem_filter_help)
        self.language_button.clicked.connect(self._cycle_language)
        self.theme_button.clicked.connect(self._cycle_theme)
        self.recursive_button.toggled.connect(self._recursive_changed)
        self.case_button.toggled.connect(self._case_changed)
        self.regex_button.toggled.connect(self._regex_changed)
        self.line_wrap_button.toggled.connect(self._line_wrap_changed)
        self.scope_button.clicked.connect(self._cycle_search_scope)
        self.highlight_button.toggled.connect(self._toggle_highlight_panel)
        self.cache_button.clicked.connect(self._clear_word_cache)
        self.export_word_button.clicked.connect(self._choose_word_export)
        self.folder_edit.textChanged.connect(self._queue_word_scan)
        self.stem_filter_edit.textChanged.connect(self._queue_word_scan)
        self.custom_color_button.clicked.connect(self._choose_highlight_color)
        self.file_list.currentItemChanged.connect(self._file_selected)
        self.match_list.currentItemChanged.connect(self._match_selected)

    def _restore_window_state(self) -> None:
        main_splitter_state = self.settings.value("window/main_splitter")
        if main_splitter_state:
            self.main_splitter.restoreState(main_splitter_state)
        result_splitter_state = self.settings.value("window/result_splitter")
        if result_splitter_state:
            self.result_splitter.restoreState(result_splitter_state)

    def t(self, key: str, **values: object) -> str:
        return translate(self.language, key, **values)

    def retranslate_ui(self) -> None:
        self.search_area.setTitle(self.t("search_target"))
        self.folder_edit.setToolTip(self.t("drop_target_hint"))
        for label in self.findChildren(QLabel):
            key = label.property("translation_key")
            if key:
                label.setText(self.t(key))
        self.browse_button.setToolTip(self.t("browse"))
        self.stem_filter_edit.setPlaceholderText(self.t("stem_filter_hint"))
        self.stem_filter_edit.setToolTip(self.t("stem_filter_help"))
        self.stem_filter_edit.setAccessibleName(self.t("stem_filter"))
        self.stem_filter_help_button.setToolTip(self.t("stem_filter_help_title"))
        self.stem_filter_help_content.setText(self.t("stem_filter_help_content"))
        self.pattern_edit.setPlaceholderText(self.t("pattern_hint"))
        self.pattern_help_button.setToolTip(self.t("pattern_help"))
        self.pattern_help_button.setAccessibleName(self.t("pattern_help"))
        self.pattern_help_content.setText(self.t("pattern_help_content"))
        self.settings_toolbar.setWindowTitle(self.t("settings"))
        self.cache_button.setToolTip(self.t("clear_word_cache"))
        self.cache_button.setAccessibleName(self.t("clear_word_cache"))
        self.export_word_button.setToolTip(self.t("export_word"))
        self._refresh_settings_buttons()
        self.highlight_panel_label.setText(self.t("common_colors"))
        self.custom_color_button.setToolTip(self.t("custom_color"))
        self.search_button.setToolTip(self.t("search"))
        self.cancel_button.setToolTip(self.t("cancel"))
        self.file_group.setTitle(self.t("files"))
        self.match_group.setTitle(self.t("matches"))
        self.file_list.setHeaderLabels([self.t("filename"), self.t("count")])
        self.match_list.setHeaderLabels([self.t("page_number"), self.t("paragraph")])
        self.preview_group.setTitle(self.t("preview"))
        self.preview.set_language(self.language)
        self._refresh_highlight_swatches()
        if self.worker is not None:
            self._refresh_search_status()
        elif self.export_worker is not None and self._export_progress_state is not None:
            self._export_progress(*self._export_progress_state)
        elif self.folder_edit.text() and not self._folder_available():
            self._set_status(self.t("folder_missing"))
        elif not self.documents:
            self._set_status(self.t("ready"))
        self._refresh_result_labels()

    def _choose_folder(self):
        self.host.choose_folder()

    def _set_folder(self, folder: Path) -> None:
        self.folder_edit.setText(str(folder))
        self.settings.setValue("search/folder", str(folder))
        self._queue_word_scan()

        self.changed.emit()

    def _queue_word_scan(self) -> None:
        self._word_scan_request += 1
        self._export_paths = []
        self.export_word_button.setEnabled(False)
        valid = self._folder_available()
        self.search_button.setEnabled(not self.is_busy() and valid)
        if self.folder_edit.text() and not valid and not self.is_busy():
            self._set_status(self.t("folder_missing"))
        self._word_scan_timer.start()

    def _scan_export_files(self) -> None:
        if self._closing:
            return
        root = Path(self.folder_edit.text()) if self.folder_edit.text() else None
        worker = WordFileScanWorker(self._word_scan_request, root,
                                    self.recursive_button.isChecked(), self.stem_filter_edit.text())
        worker.signals.finished.connect(self._export_files_scanned)
        self._word_scans[worker.request] = worker
        self.thread_pool.start(worker)

    def _export_files_scanned(self, request: int, paths: list[Path]) -> None:
        self._word_scans.pop(request, None)
        if request != self._word_scan_request or self._closing:
            return
        self._export_paths = paths
        watched = self._export_watcher.directories()
        if watched:
            self._export_watcher.removePaths(watched)
        root = Path(self.folder_edit.text()) if self.folder_edit.text() else None
        folders = {path.parent for path in paths}
        if root is not None and root.is_dir():
            folders.add(root)
        if folders:
            self._export_watcher.addPaths([str(folder) for folder in folders if folder.is_dir()])
        self.export_word_button.setEnabled(bool(paths) and self.worker is None and self.export_worker is None)

    def _choose_word_export(self) -> None:
        if self._closing or self.worker is not None or self.export_worker is not None or not self._export_paths:
            return
        root = Path(self.folder_edit.text())
        dialog = WordExportDialog(root, self._export_paths,
                                  self.settings.value("export/folder", str(root), type=str), self.language, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        destination = Path(dialog.destination.text())
        self.settings.setValue("export/folder", str(destination))
        worker = WordExportWorker(dialog.selected_paths(), destination, dialog.overwrite.isChecked(), self.host.conversions.prepare)
        self.export_worker = worker
        worker.signals.progress.connect(lambda *args: self._export_progress(*args)
                                        if self.export_worker is worker and not self._closing else None)
        worker.signals.finished.connect(lambda report: self._export_finished(report)
                                        if self.export_worker is worker else None)
        self._set_searching(True)
        self.progress_bar.setRange(0, len(worker.paths))
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self._set_status(self.t("export_progress", current=0, total=len(worker.paths), name=""))
        self.thread_pool.start(worker)

    def _export_progress(self, current: int, total: int, name: str) -> None:
        if self._closing:
            return
        self._export_progress_state = (current, total, name)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self._set_status(self.t("export_progress", current=current + 1, total=total, name=name))

    def _export_finished(self, report: ExportReport) -> None:
        self.export_worker = None
        self._export_progress_state = None
        if self._closing:
            self.changed.emit()
            return
        self._set_searching(False)
        self.progress_bar.hide()
        key = "export_cancelled" if report.cancelled else "export_done"
        self._set_status(self.t(key, exported=report.exported, skipped=report.skipped, failed=len(report.errors)))
        if report.errors:
            QMessageBox.warning(self, self.t("export_word"),
                                "\n".join(f"{path}: {message}" for path, message in report.errors))
        self._queue_word_scan()

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

        self.changed.emit()

    def _options(self) -> SearchOptions:
        return SearchOptions(
            root=Path(self.folder_edit.text()),
            pattern=self.pattern_edit.text(),
            use_regex=self.regex_button.isChecked(),
            case_sensitive=self.case_button.isChecked(),
            recursive=self.recursive_button.isChecked(),
            search_scope=self.search_scope,
            stem_glob=self.stem_filter_edit.text(),
            ignore_line_wraps=self.line_wrap_button.isChecked(),
        )

    def _start_search(self) -> None:
        if self._closing or self.worker is not None or self.export_worker is not None:
            return
        options = self._options()
        try:
            compile_pattern(options)
            if not options.root.is_dir():
                raise SearchInputError(self.t("choose_folder"))
        except SearchInputError as exc:
            QMessageBox.warning(self, self.t("invalid"), str(exc))
            return

        self.settings.setValue("search/folder", str(options.root))
        self._save_pattern()
        self._save_stem_filter()
        self.settings.setValue("search/recursive", options.recursive)
        self.settings.setValue("search/scope", options.search_scope)
        self.documents = []
        self._pending_errors.clear()
        self._document_indexes = {}
        self.file_list.clear()
        self.match_list.clear()
        self.preview.clear()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self._search_progress_state = None
        self._screening_state = None
        self._candidate_count = 0
        self._converting_word_name = ""
        self._set_status(self.t("preparing_search"))
        self._set_searching(True)

        worker = SearchWorker(options, passwords=self._pdf_passwords, conversion_service=self.host.conversions)
        worker.signals.password_required.connect(
            lambda request, owner=worker: self._request_pdf_password(owner, request)
        )
        for signal, callback in (
            (worker.signals.screening, self._screening_progress),
            (worker.signals.candidate_found, self._candidate_found),
            (worker.signals.progress, self._search_progress),
            (worker.signals.converting, self._word_converting),
            (worker.signals.preliminary, self._preliminary_found),
            (worker.signals.resolved, self._document_resolved),
            (worker.signals.match_found, self._match_found),
        ):
            signal.connect(lambda *args, target=callback: target(*args)
                           if self.worker is worker and not self._closing else None)
        worker.signals.finished.connect(lambda report: self._search_finished(report)
                                        if self.worker is worker else None)
        worker.signals.failed.connect(lambda message: self._search_failed(message)
                                      if self.worker is worker else None)
        self.worker = worker
        self.thread_pool.start(worker)

    def _cancel_search(self) -> None:
        if self.export_worker is not None:
            self.export_worker.cancel()
            self.cancel_button.setEnabled(False)
        if self.worker is not None:
            self.worker.cancel()
            if self._password_dialog is not None:
                self._password_dialog.reject()
            self.cancel_button.setEnabled(False)

    def _request_pdf_password(self, owner: SearchWorker, request: PdfPasswordRequest) -> None:
        if self._closing or self.worker is not owner or owner.cancel_event.is_set():
            request.complete(None)
            return
        dialog = QInputDialog(self)
        dialog.setWindowTitle(self.t("pdf_password_title"))
        key = "pdf_password_incorrect" if request.incorrect else "pdf_password_prompt"
        dialog.setLabelText(self.t(key, name=request.path.name))
        dialog.setToolTip(str(request.path))
        dialog.setTextEchoMode(QLineEdit.EchoMode.Password)
        dialog.setOkButtonText(self.t("pdf_unlock"))
        dialog.setCancelButtonText(self.t("pdf_skip"))
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        self._password_dialog = dialog

        def finished(result: int) -> None:
            accepted = (result == QInputDialog.DialogCode.Accepted and not self._closing
                        and self.worker is owner and not owner.cancel_event.is_set())
            request.complete(dialog.textValue() if accepted else None)
            dialog.setTextValue("")
            if self._password_dialog is dialog:
                self._password_dialog = None
            dialog.deleteLater()

        dialog.finished.connect(finished)
        dialog.show()

    def _set_searching(self, active: bool) -> None:
        for widget in (
            self.stem_filter_edit,
            self.pattern_edit,
            self.regex_button,
            self.line_wrap_button,
            self.case_button,
            self.recursive_button,
            self.scope_button,
            self.cache_button,
            self.search_button,
        ):
            widget.setEnabled(not active)
        self.cancel_button.setEnabled(active)
        key = "export_cancel" if self.export_worker is not None else "cancel"
        self.cancel_button.setToolTip(self.t(key))
        self.cache_button.setEnabled(not active and not self.host.any_busy())
        self.export_word_button.setEnabled(not active and bool(self._export_paths))
        self.search_button.setEnabled(not active and self._folder_available())

        self.changed.emit()

    def _search_progress(self, current: int, total: int, name: str) -> None:
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(current - 1)
        self._search_progress_state = (current, total, name)
        self._refresh_search_status()

    def _word_converting(self, name: str) -> None:
        self._converting_word_name = name
        self._refresh_search_status()

    def _screening_progress(self, current: int, total: int, name: str) -> None:
        self._screening_state = (current, total, name)
        self._refresh_search_status()

    def _candidate_found(self, name: str, count: int) -> None:
        self._candidate_count = count
        self._refresh_search_status()

    def _refresh_search_status(self) -> None:
        if self.worker is None:
            return
        stages = []
        if self._screening_state is not None:
            current, total, name = self._screening_state
            stages.append(self.t("screening_word", current=current, total=total,
                                 candidates=self._candidate_count, name=name))
        if self._search_progress_state is not None:
            current, total, name = self._search_progress_state
            stages.append(self.t("searching", current=current, total=total, name=name))
        if self._converting_word_name:
            stages.append(self.t("converting_word", name=self._converting_word_name))
        pending = sum(isinstance(doc, PreliminaryDocument) and doc.path not in self._pending_errors
                      for doc in self.documents)
        if pending and self._screening_state is not None and self._screening_state[0] >= self._screening_state[1]:
            stages.append(self.t("initial_search_done", count=pending))
        self._set_status("; ".join(stages) if stages else self.t("preparing_search"))

    def _match_found(
        self, path: Path, relative_path: Path, preview_path: Path, match
    ) -> None:
        index = self._document_indexes.get(path)
        if index is not None and isinstance(self.documents[index], PreliminaryDocument):
            return
        if index is None:
            index = len(self.documents)
            self._document_indexes[path] = index
            document = DocumentMatch(path, relative_path, (match,), preview_path)
            self.documents.append(document)
            self._append_file(document, index)
            return

        previous = self.documents[index]
        document = DocumentMatch(
            path, relative_path, previous.matches + (match,), preview_path
        )
        self.documents[index] = document
        file_item = self.file_list.topLevelItem(index)
        file_item.setText(1, str(len(document.matches)))
        if self.file_list.currentItem() is file_item:
            self._append_match(match, len(document.matches) - 1)

    def _search_finished(self, report: SearchReport) -> None:
        self.worker = None
        if self._closing:
            self.changed.emit()
            return
        self._set_searching(False)
        self.progress_bar.setVisible(False)
        failed = [doc for doc in self.documents if isinstance(doc, PreliminaryDocument)
                  and doc.path in self._pending_errors] if not report.cancelled else []
        finished_documents = report.documents + failed
        received_matches = sum(len(document.matches) for document in self.documents)
        report_matches = sum(len(document.matches) for document in report.documents)
        if len(self.documents) != len(finished_documents) or received_matches != report_matches:
            self.documents = finished_documents
            self._populate_files()
        else:
            self.documents = finished_documents
        self._document_indexes = {
            document.path: index for index, document in enumerate(self.documents)
        }
        total_matches = sum(len(document.matches) for document in report.documents)
        if report.cancelled:
            self._set_status(self.t("cancelled", scanned=report.scanned_files))
        elif not report.documents:
            self._set_status(self.t("no_results"))
        else:
            self._set_status(
                self.t(
                    "done",
                    scanned=report.scanned_files,
                    files=len(report.documents),
                    matches=total_matches,
                )
            )
        if report.warnings:
            details = "\n".join(
                f"• {warning.path.name}: {warning.message}" for warning in report.warnings[:12]
            )
            if len(report.warnings) > 12:
                details += f"\n… +{len(report.warnings) - 12}"
            self.status_label.setToolTip(self.status_label.text() + "\n" + details)
            if self.host.current_tab is self:
                QMessageBox.warning(self, self.t("warnings"),
                                    self.t("warning_body", count=len(report.warnings), details=details))

    def _search_failed(self, message: str) -> None:
        self.worker = None
        if self._closing:
            self.changed.emit()
            return
        self._set_searching(False)
        self.progress_bar.setVisible(False)
        self._set_status(self.t("ready"))
        QMessageBox.critical(self, self.t("invalid"), message)

    def _populate_files(self) -> None:
        self.file_list.clear()
        for index, document in enumerate(self.documents):
            self._append_file(document, index, select_first=False)
        if self.file_list.topLevelItemCount():
            self.file_list.setCurrentItem(self.file_list.topLevelItem(0))

    def _append_file(
        self, document: DocumentMatch | PreliminaryDocument, index: int, *, select_first: bool = True
    ) -> None:
        count = self.t("pending_count", count=len(document.matches)) if isinstance(document, PreliminaryDocument) and document.matches else self.t("pending_page") if isinstance(document, PreliminaryDocument) else str(len(document.matches))
        if document.path in self._pending_errors:
            count = self.t("conversion_failed")
        item = QTreeWidgetItem([str(document.relative_path), count])
        item.setData(0, Qt.ItemDataRole.UserRole, index)
        item.setToolTip(0, str(document.path))
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.file_list.addTopLevelItem(item)
        if select_first and self.file_list.currentItem() is None:
            self.file_list.setCurrentItem(item)

    def _file_selected(self, item: QTreeWidgetItem | None, _previous=None) -> None:
        self.match_list.clear()
        self.preview.clear()
        row = self.file_list.indexOfTopLevelItem(item) if item is not None else -1
        if row < 0 or row >= len(self.documents):
            return
        document = self.documents[row]
        for index, match in enumerate(document.matches):
            self._append_match(match, index, select_first=False)
        if self.match_list.topLevelItemCount():
            self.match_list.setCurrentItem(self.match_list.topLevelItem(0))

        if isinstance(document, PreliminaryDocument) and not document.matches:
            self.preview.show_pending(self.t("preview_queued", ahead=0))
            self._refresh_pending_preview()

    def _append_match(self, match, index: int, *, select_first: bool = True) -> None:
        if isinstance(match, PreliminaryMatch):
            page_text = self.t("pending_page")
        elif match.start_page == match.end_page:
            page_text = str(match.start_page + 1)
        else:
            page_text = f"{match.start_page + 1}–{match.end_page + 1}"
        match_item = QTreeWidgetItem([page_text, match.context])
        match_item.setData(0, Qt.ItemDataRole.UserRole, index)
        match_item.setToolTip(1, match.matched_text)
        match_item.setTextAlignment(
            0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.match_list.addTopLevelItem(match_item)
        if select_first and self.match_list.currentItem() is None:
            self.match_list.setCurrentItem(match_item)

    def _match_selected(self, item: QTreeWidgetItem | None, _previous=None) -> None:
        current_file = self.file_list.currentItem()
        file_row = self.file_list.indexOfTopLevelItem(current_file) if current_file else -1
        if file_row < 0 or file_row >= len(self.documents):
            return
        document = self.documents[file_row]
        row = self.match_list.indexOfTopLevelItem(item) if item is not None else -1
        if row < 0 or row >= len(document.matches):
            self.preview.clear()
            return
        if isinstance(document, PreliminaryDocument):
            self.preview.show_pending(self.t("preview_queued", ahead=0))
            self._refresh_pending_preview()
            return
        self.preview.show_match(
            str(document.preview_path or document.path), document.matches[row]
        )

    def _refresh_result_labels(self) -> None:
        for i, document in enumerate(self.documents):
            item = self.file_list.topLevelItem(i)
            if item is not None and isinstance(document, PreliminaryDocument):
                text = self.t("pending_count", count=len(document.matches)) if document.matches else self.t("pending_page")
                item.setText(1, self.t("conversion_failed") if document.path in self._pending_errors else text)
        for i in range(self.match_list.topLevelItemCount()):
            item = self.match_list.topLevelItem(i)
            if not item.text(0)[0:1].isdigit():
                item.setText(0, self.t("pending_page"))

    def _cycle_language(self):
        self.host._cycle_language()

    def _cycle_theme(self):
        self.host._cycle_theme()

    def _recursive_changed(self, checked: bool) -> None:
        self.settings.setValue("search/recursive", checked)
        self._refresh_settings_buttons()
        self._queue_word_scan()

    def _case_changed(self, checked: bool) -> None:
        self.settings.setValue("search/case_sensitive", checked)
        self._refresh_settings_buttons()

    def _line_wrap_changed(self, checked: bool) -> None:
        self.settings.setValue("search/ignore_line_wraps", checked)
        self._refresh_settings_buttons()

    def _regex_changed(self, checked: bool) -> None:
        self.settings.setValue("search/use_regex", checked)
        self._refresh_settings_buttons()

    def _cycle_search_scope(self) -> None:
        scopes = ("pdf", "word", "all")
        self.search_scope = scopes[(scopes.index(self.search_scope) + 1) % len(scopes)]
        self.settings.setValue("search/scope", self.search_scope)
        self._refresh_settings_buttons()

    def _save_stem_filter(self) -> None:
        self.settings.setValue("search/stem_glob", self.stem_filter_edit.text())

    def _save_pattern(self) -> None:
        self.settings.setValue("search/pattern", self.pattern_edit.text())

    def _clear_word_cache(self):
        self.host._clear_word_cache()

    def _show_stem_filter_help(self) -> None:
        position = self.stem_filter_help_button.rect().bottomLeft()
        self.stem_filter_help_menu.popup(self.stem_filter_help_button.mapToGlobal(position))

    def _show_pattern_help(self) -> None:
        position = self.pattern_help_button.rect().bottomLeft()
        self.pattern_help_menu.popup(self.pattern_help_button.mapToGlobal(position))

    def _toggle_highlight_panel(self, expanded: bool) -> None:
        self.highlight_panel.setVisible(expanded)
        self._refresh_settings_buttons()

    def _refresh_settings_buttons(self) -> None:
        language_labels = {
            "system": self.t("system"),
            "zh_TW": self.t("traditional_chinese"),
            "en": self.t("english"),
        }
        self.language_button.set_icon_kind(
            {
                "system": "language_system",
                "zh_TW": "language_zh",
                "en": "language_en",
            }[self.language_preference]
        )
        self.language_button.setToolTip(
            f"{self.t('language')}：{language_labels[self.language_preference]}"
        )
        self.language_button.setAccessibleName(self.language_button.toolTip())
        self.theme_button.set_icon_kind(
            {"system": "theme_system", "light": "sun", "dark": "moon"}[
                self.theme_preference
            ]
        )
        self.theme_button.setToolTip(
            f"{self.t('theme')}：{self.t(self.theme_preference)}"
        )
        self.theme_button.setAccessibleName(self.theme_button.toolTip())
        self.recursive_button.set_icon_kind("recursive")
        self.recursive_button.setToolTip(
            f"{self.t('recursive')}：{self.t('enabled' if self.recursive_button.isChecked() else 'disabled')}"
        )
        self.recursive_button.setAccessibleName(self.recursive_button.toolTip())
        self.case_button.set_icon_kind("case")
        self.case_button.setToolTip(
            f"{self.t('case')}：{self.t('enabled' if self.case_button.isChecked() else 'disabled')}"
        )
        self.case_button.setAccessibleName(self.case_button.toolTip())
        self.line_wrap_button.setToolTip(
            f"{self.t('ignore_line_wraps')}：{self.t('enabled' if self.line_wrap_button.isChecked() else 'disabled')}"
        )
        self.regex_button.set_icon_kind("regex")
        self.regex_button.setToolTip(
            f"{self.t('regex')}：{self.t('enabled' if self.regex_button.isChecked() else 'disabled')}"
        )
        self.regex_button.setAccessibleName(self.regex_button.toolTip())
        self.scope_button.set_icon_kind(f"scope_{self.search_scope}")
        self.scope_button.setToolTip(
            f"{self.t('file_types')}：{self.t(f'scope_{self.search_scope}')}"
        )
        self.scope_button.setAccessibleName(self.scope_button.toolTip())
        self.highlight_button.set_icon_kind("highlighter")
        self.highlight_button.setToolTip(self.t("highlight_settings"))
        self.highlight_button.setAccessibleName(self.highlight_button.toolTip())
        self.highlight_button.icon_foreground = QColor(self.highlight_color)
        self.highlight_button.setStyleSheet("")
        self.highlight_button.update()

    def _choose_highlight_color(self) -> None:
        color = QColorDialog.getColor(
            self.highlight_color, self, self.t("choose_highlight_color")
        )
        if color.isValid():
            self._set_highlight_color(color.name())

    def _set_highlight_color(self, color_value):
        self.host._set_highlight_color(color_value)

    def _refresh_highlight_swatches(self) -> None:
        selected = self.highlight_color.name()
        self.highlight_color_value.setText(selected.upper())
        for color, button in self.highlight_swatches.items():
            is_selected = color == selected
            button.set_icon_kind("check" if is_selected else "")
            button.icon_foreground = QColor("#202124")
            button.setToolTip(color.upper())
            button.setStyleSheet(
                "QToolButton {"
                f"background-color: {color}; color: #202124;"
                f"border: {'2px solid palette(highlight)' if is_selected else '1px solid palette(mid)'};"
                "border-radius: 14px; padding: 0; font-weight: 700;"
                "}"
            )

    def is_busy(self):
        return self.worker is not None or self.export_worker is not None

    def _folder_available(self):
        try:
            return bool(self.folder_edit.text()) and Path(self.folder_edit.text()).is_dir()
        except OSError:
            return False

    def settled(self):
        return not self.is_busy() and self.thread_pool.activeThreadCount() == 0 and not self.preview._workers

    def shutdown(self):
        self._closing = True
        self._word_scan_timer.stop()
        self._pending_timer.stop()
        watched = self._export_watcher.directories()
        if watched:
            self._export_watcher.removePaths(watched)
        self._cancel_search()
        if self.thread_pool.activeThreadCount() == 0:
            self.worker = None
            self.export_worker = None
        if self._password_dialog is not None:
            self._password_dialog.reject()
        self.preview.clear()

    def snapshot(self):
        self._save_pattern()
        self._save_stem_filter()
        self.settings.setValue("window/main_splitter", self.main_splitter.saveState())
        self.settings.setValue("window/result_splitter", self.result_splitter.saveState())
        return dict(self.settings.state.values)

    def _preliminary_found(self, document):
        if self._closing:
            return
        index = len(self.documents)
        self._document_indexes[document.path] = index
        self.documents.append(document)
        self._append_file(document, index)
        self._refresh_search_status()

    def _document_resolved(self, path, result, error):
        if self._closing:
            return
        index = self._document_indexes.get(path)
        if index is None:
            return
        current = self.file_list.currentItem()
        row = self.file_list.indexOfTopLevelItem(current) if current else -1
        selected = self.documents[row].path if 0 <= row < len(self.documents) else None
        match_item = self.match_list.currentItem()
        selected_text = match_item.toolTip(1) if match_item else ""
        if error:
            self._pending_errors[path] = error
            if selected == path:
                self.preview.show_pending(self.t("preview_failed", message=error), animate=False)
            return
        if result is not None and result.matches:
            self.documents[index] = result
        else:
            self.documents.pop(index)
        self._document_indexes = {doc.path: i for i, doc in enumerate(self.documents)}
        self.file_list.blockSignals(True)
        self.file_list.clear()
        for i, document in enumerate(self.documents):
            self._append_file(document, i, select_first=False)
        target = self._document_indexes.get(selected, 0)
        item = self.file_list.topLevelItem(target)
        self.file_list.setCurrentItem(item)
        self.file_list.blockSignals(False)
        if selected == path:
            self._file_selected(item)
            for i in range(self.match_list.topLevelItemCount()):
                match = self.match_list.topLevelItem(i)
                if match.toolTip(1) == selected_text:
                    self.match_list.setCurrentItem(match)
                    break

    def _refresh_pending_preview(self):
        if self._closing or not self.isVisible():
            return
        item = self.file_list.currentItem()
        row = self.file_list.indexOfTopLevelItem(item) if item else -1
        if not 0 <= row < len(self.documents):
            return
        document = self.documents[row]
        if not isinstance(document, PreliminaryDocument):
            return
        if document.path in self._pending_errors:
            self.preview.show_pending(self.t("preview_failed", message=self._pending_errors[document.path]), animate=False)
            return
        state, ahead = self.host.conversions.state(document.path)
        key = {"queued": "preview_queued", "converting": "preview_converting"}.get(state, "preview_confirming")
        self.preview.update_pending(self.t(key, ahead=ahead))
