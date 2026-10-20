# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QLocale, QSettings, Qt, QThreadPool
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QColorDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QHeaderView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from rgpdf import __version__
from rgpdf.buttons import SettingsButton
from rgpdf.i18n import translate
from rgpdf.models import DocumentMatch, SearchOptions, SearchReport
from rgpdf.preview import PdfPreview
from rgpdf.resources import application_icon
from rgpdf.search import SearchInputError, compile_pattern
from rgpdf.worker import SearchWorker
from rgpdf.word_conversion import clear_word_cache


class SettingsToolBar(QToolBar):
    """Keep control spacing and margins stable when Qt reapplies style metrics."""

    def event(self, event) -> bool:
        handled = super().event(event)
        if event.type() in (
            QEvent.Type.Polish,
            QEvent.Type.Show,
            QEvent.Type.StyleChange,
        ):
            layout = self.layout()
            if layout is not None:
                layout.setSpacing(SettingsButton.SPACING)
                padding = SettingsButton.PADDING
                layout.setContentsMargins(padding, padding, padding, padding)
        return handled


class MainWindow(QMainWindow):
    LANGUAGE_CYCLE = ("system", "zh_TW", "en")
    THEME_CYCLE = ("system", "light", "dark")

    def __init__(self, apply_theme_callback, settings: QSettings | None = None) -> None:
        super().__init__()
        self.settings = settings or QSettings("rgpdf", "rgpdf")
        self.apply_theme_callback = apply_theme_callback
        self.thread_pool = QThreadPool.globalInstance()
        self.worker: SearchWorker | None = None
        self._search_progress_state: tuple[int, int, str] | None = None
        self._converting_word_name = ""
        self._screening_state = None
        self._candidate_count = 0
        self.documents: list[DocumentMatch] = []
        self._document_indexes: dict[Path, int] = {}
        self.language_preference = self._initial_language_preference()
        self.language = self._resolved_language(self.language_preference)
        stored_theme = self.settings.value("appearance/theme", "system", type=str)
        self.theme_preference = stored_theme if stored_theme in self.THEME_CYCLE else "system"
        self.setWindowIcon(application_icon())
        stored_highlight = self.settings.value(
            "appearance/highlight_color", "#ffe128", type=str
        )
        self.highlight_color = QColor(stored_highlight)
        if not self.highlight_color.isValid():
            self.highlight_color = QColor("#ffe128")

        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.browse_button = SettingsButton("browse")
        self.stem_filter_edit = QLineEdit()
        self.stem_filter_edit.setText(
            self.settings.value("search/stem_glob", "", type=str)
        )
        stored_scope = self.settings.value("search/scope", "pdf", type=str)
        if stored_scope not in {"pdf", "word", "all"}:
            stored_scope = "pdf"
        self.search_scope = stored_scope
        self.scope_button = self._settings_button()
        self.pattern_edit = QLineEdit()
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
        self.about_button = self._settings_button()
        self.about_button.set_icon_kind("about")
        self.search_button = SettingsButton("search")
        self.cancel_button = SettingsButton("cancel")
        self.cancel_button.setEnabled(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

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

        self.search_area = QFrame()
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
        ):
            self.settings_toolbar.addWidget(button)
        self.settings_toolbar.addSeparator()
        for button in (
            self.language_button,
            self.theme_button,
        ):
            self.settings_toolbar.addWidget(button)
        self.settings_toolbar.addSeparator()
        self.settings_toolbar.addWidget(self.about_button)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.settings_toolbar)

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

        progress_row = QHBoxLayout()
        progress_row.addWidget(self.status_label, 1)
        progress_row.addWidget(self.progress_bar)

        self.file_group = QGroupBox()
        self.match_group = QGroupBox()
        self.preview_group = QGroupBox()
        self.file_list = self._result_table()
        self.match_list = self._result_table()
        self.file_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.match_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.match_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.preview = PdfPreview()
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
        left_layout.addLayout(progress_row)
        left_layout.addWidget(self.result_splitter, 1)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self.preview_group)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setHandleWidth(12)
        self.main_splitter.setSizes([620, 660])

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(12, 8, 12, 12)
        root_layout.addWidget(self.highlight_panel)
        root_layout.addWidget(self.main_splitter, 1)
        central = QWidget()
        central.setObjectName("centralWidget")
        central.setLayout(root_layout)
        self.setCentralWidget(central)

        self._connect_signals()
        self._restore_window_state()
        self.retranslate_ui()

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
        self.about_button.clicked.connect(self._show_about)
        self.custom_color_button.clicked.connect(self._choose_highlight_color)
        self.file_list.currentItemChanged.connect(self._file_selected)
        self.match_list.currentItemChanged.connect(self._match_selected)

    def _restore_window_state(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1280, 780)
        main_splitter_state = self.settings.value("window/main_splitter")
        if main_splitter_state:
            self.main_splitter.restoreState(main_splitter_state)
        result_splitter_state = self.settings.value("window/result_splitter")
        if result_splitter_state:
            self.result_splitter.restoreState(result_splitter_state)

    def t(self, key: str, **values: object) -> str:
        return translate(self.language, key, **values)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.t("app_title", version=__version__))
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
        self.about_button.setToolTip(self.t("about"))
        self.about_button.setAccessibleName(self.t("about"))
        self.cache_button.setToolTip(self.t("clear_word_cache"))
        self.cache_button.setAccessibleName(self.t("clear_word_cache"))
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
        elif not self.documents:
            self.status_label.setText(self.t("ready"))
        self._refresh_result_labels()

    def _choose_folder(self) -> None:
        starting_path = self.folder_edit.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, self.t("choose_folder"), starting_path)
        if folder:
            self.folder_edit.setText(folder)
            self.settings.setValue("search/folder", folder)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            self.t("about_title"),
            self.t("about_content", version=__version__),
        )

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
        if self.worker is not None:
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
        self.status_label.setText(self.t("preparing_search"))
        self._set_searching(True)

        worker = SearchWorker(options)
        worker.signals.screening.connect(self._screening_progress)
        worker.signals.candidate_found.connect(self._candidate_found)
        worker.signals.progress.connect(self._search_progress)
        worker.signals.converting.connect(self._word_converting)
        worker.signals.match_found.connect(self._match_found)
        worker.signals.finished.connect(self._search_finished)
        worker.signals.failed.connect(self._search_failed)
        self.worker = worker
        self.thread_pool.start(worker)

    def _cancel_search(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)

    def _set_searching(self, active: bool) -> None:
        for widget in (
            self.browse_button,
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
        self.cache_button.setEnabled(not active)

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
        self.status_label.setText("; ".join(stages) if stages else self.t("preparing_search"))

    def _match_found(
        self, path: Path, relative_path: Path, preview_path: Path, match
    ) -> None:
        index = self._document_indexes.get(path)
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
        self._set_searching(False)
        self.progress_bar.setVisible(False)
        received_matches = sum(len(document.matches) for document in self.documents)
        report_matches = sum(len(document.matches) for document in report.documents)
        if len(self.documents) != len(report.documents) or received_matches != report_matches:
            self.documents = report.documents
            self._populate_files()
        else:
            self.documents = report.documents
        self._document_indexes = {
            document.path: index for index, document in enumerate(self.documents)
        }
        total_matches = sum(len(document.matches) for document in report.documents)
        if report.cancelled:
            self.status_label.setText(self.t("cancelled", scanned=report.scanned_files))
        elif not report.documents:
            self.status_label.setText(self.t("no_results"))
        else:
            self.status_label.setText(
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
            QMessageBox.warning(
                self,
                self.t("warnings"),
                self.t("warning_body", count=len(report.warnings), details=details),
            )

    def _search_failed(self, message: str) -> None:
        self.worker = None
        self._set_searching(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText(self.t("ready"))
        QMessageBox.critical(self, self.t("invalid"), message)

    def _populate_files(self) -> None:
        self.file_list.clear()
        for index, document in enumerate(self.documents):
            self._append_file(document, index, select_first=False)
        if self.file_list.topLevelItemCount():
            self.file_list.setCurrentItem(self.file_list.topLevelItem(0))

    def _append_file(
        self, document: DocumentMatch, index: int, *, select_first: bool = True
    ) -> None:
        item = QTreeWidgetItem([str(document.relative_path), str(len(document.matches))])
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

    def _append_match(self, match, index: int, *, select_first: bool = True) -> None:
        if match.start_page == match.end_page:
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
        self.preview.show_match(
            str(document.preview_path or document.path), document.matches[row]
        )

    def _refresh_result_labels(self) -> None:
        if not self.documents:
            return
        file_item = self.file_list.currentItem()
        match_item = self.match_list.currentItem()
        file_row = self.file_list.indexOfTopLevelItem(file_item) if file_item else -1
        match_row = self.match_list.indexOfTopLevelItem(match_item) if match_item else -1
        self._populate_files()
        if file_row >= 0:
            file_row = min(file_row, self.file_list.topLevelItemCount() - 1)
            self.file_list.setCurrentItem(self.file_list.topLevelItem(file_row))
            if match_row >= 0:
                match_row = min(match_row, self.match_list.topLevelItemCount() - 1)
                self.match_list.setCurrentItem(self.match_list.topLevelItem(match_row))

    def _cycle_language(self) -> None:
        index = self.LANGUAGE_CYCLE.index(self.language_preference)
        self.language_preference = self.LANGUAGE_CYCLE[
            (index + 1) % len(self.LANGUAGE_CYCLE)
        ]
        self.settings.setValue("appearance/language", self.language_preference)
        self.language = self._resolved_language(self.language_preference)
        self.retranslate_ui()

    def _cycle_theme(self) -> None:
        index = self.THEME_CYCLE.index(self.theme_preference)
        self.theme_preference = self.THEME_CYCLE[(index + 1) % len(self.THEME_CYCLE)]
        self.settings.setValue("appearance/theme", self.theme_preference)
        self.apply_theme_callback(self.theme_preference)
        self._refresh_settings_buttons()

    def _recursive_changed(self, checked: bool) -> None:
        self.settings.setValue("search/recursive", checked)
        self._refresh_settings_buttons()

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

    def _clear_word_cache(self) -> None:
        answer = QMessageBox.question(
            self,
            self.t("clear_word_cache"),
            self.t("clear_cache_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.preview.clear()
        result = clear_word_cache()
        QMessageBox.information(
            self,
            self.t("clear_word_cache"),
            self.t(
                "cache_cleared_body",
                count=result.removed_files,
                size=f"{result.removed_bytes / (1024 * 1024):.1f}",
                failed=result.failed_files,
            ),
        )

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

    def _set_highlight_color(self, color_value: str) -> None:
        color = QColor(color_value)
        if not color.isValid():
            return
        self.highlight_color = color
        self.settings.setValue("appearance/highlight_color", color.name())
        self.preview.set_highlight_color(color.name())
        self._refresh_highlight_swatches()
        if self.highlight_button.isChecked():
            self.highlight_button.setChecked(False)
        else:
            self._refresh_settings_buttons()

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

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self.worker is not None:
            self.worker.cancel()
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/main_splitter", self.main_splitter.saveState())
        self.settings.setValue("window/result_splitter", self.result_splitter.saveState())
        self._save_pattern()
        self._save_stem_filter()
        self.preview.clear()
        super().closeEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.LocaleChange
            and self.language_preference == "system"
        ):
            resolved = self._resolved_language("system")
            if resolved != self.language:
                self.language = resolved
                self.retranslate_ui()
