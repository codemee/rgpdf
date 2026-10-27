# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from rgpdf.buttons import SettingsButton
from rgpdf.i18n import translate
from rgpdf.word_export import duplicate_pdf_names


class WordExportDialog(QDialog):
    def __init__(self, root: Path, paths: list[Path], destination: str, language: str, parent=None):
        super().__init__(parent)
        self.paths, self.language = paths, language
        self.setWindowTitle(self.t("export_word"))
        self.resize(640, 480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.t("export_select")))
        self.select_all = QCheckBox(self.t("export_all"))
        self.select_all.setChecked(True)
        layout.addWidget(self.select_all)
        self.files = QTreeWidget()
        self.files.setHeaderLabels([self.t("filename")])
        self.files.setRootIsDecorated(False)
        for path in paths:
            item = QTreeWidgetItem([str(path.relative_to(root))])
            item.setToolTip(0, str(path))
            item.setCheckState(0, Qt.CheckState.Checked)
            self.files.addTopLevelItem(item)
        layout.addWidget(self.files, 1)
        layout.addWidget(QLabel(self.t("export_destination")))
        row = QHBoxLayout()
        row.setSpacing(SettingsButton.SPACING)
        self.destination = QLineEdit(destination)
        self.browse = SettingsButton("browse")
        self.browse.setToolTip(self.t("export_destination"))
        row.addWidget(self.destination, 1)
        row.addWidget(self.browse)
        layout.addLayout(row)
        self.overwrite = QCheckBox(self.t("export_overwrite"))
        layout.addWidget(self.overwrite)
        actions = QHBoxLayout()
        actions.setSpacing(SettingsButton.SPACING)
        actions.addStretch()
        self.export_button = SettingsButton("export_pdf")
        self.export_button.setToolTip(self.t("export_word"))
        self.cancel_button = SettingsButton("cancel")
        self.cancel_button.setToolTip(self.t("export_cancel"))
        actions.addWidget(self.export_button)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)
        self.select_all.toggled.connect(self._check_all)
        self.files.itemChanged.connect(self._selection_changed)
        self.destination.textChanged.connect(self._update_controls)
        self.browse.clicked.connect(self._choose_destination)
        self.export_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self._update_controls()

    def t(self, key):
        return translate(self.language, key)

    def selected_paths(self):
        return [path for index, path in enumerate(self.paths)
                if self.files.topLevelItem(index).checkState(0) == Qt.CheckState.Checked]

    def _check_all(self, checked):
        self.files.blockSignals(True)
        for index in range(self.files.topLevelItemCount()):
            self.files.topLevelItem(index).setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.files.blockSignals(False)
        self._update_controls()

    def _selection_changed(self):
        self.select_all.blockSignals(True)
        self.select_all.setChecked(len(self.selected_paths()) == len(self.paths))
        self.select_all.blockSignals(False)
        self._update_controls()

    def _update_controls(self):
        self.export_button.setEnabled(bool(self.selected_paths()) and bool(self.destination.text().strip()))

    def _choose_destination(self):
        selected = QFileDialog.getExistingDirectory(self, self.t("export_destination"), self.destination.text())
        if selected:
            self.destination.setText(selected)

    def accept(self):
        if not self.selected_paths():
            return
        key = None
        if not self.destination.text().strip() or not Path(self.destination.text()).is_dir():
            key = "export_bad_destination"
        elif duplicate_pdf_names(self.selected_paths()):
            key = "export_duplicate"
        if key:
            QMessageBox.warning(self, self.t("export_word"), self.t(key))
            return
        super().accept()
