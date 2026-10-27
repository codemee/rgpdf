# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path
import sys

import pymupdf as fitz
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMimeData, QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rgpdf.buttons import SettingsButton
from rgpdf.i18n import translate
from rgpdf.models import TextMatch
from rgpdf.pdf_passwords import PdfPasswords
from rgpdf.preview_text import PageText, SelectablePageLabel, extract_page_text


class PreviewRenderSignals(QObject):
    finished = Signal(int, object, int, float, object)
    failed = Signal(int)


class PreviewRenderWorker(QRunnable):
    def __init__(
        self,
        request_id: int,
        path: Path,
        page_index: int,
        match: TextMatch,
        zoom: float,
        fit_width: bool,
        fit_page: bool,
        available_width: int,
        available_height: int,
        highlight_color: str,
        password: str | None = None,
    ) -> None:
        super().__init__()
        self.request_id = request_id
        self.path = path
        self.page_index = page_index
        self.match = match
        self.zoom = zoom
        self.fit_width = fit_width
        self.fit_page = fit_page
        self.available_width = available_width
        self.available_height = available_height
        self.highlight_color = highlight_color
        self.password = password
        self.signals = PreviewRenderSignals()

    @Slot()
    def run(self) -> None:
        try:
            with fitz.open(self.path) as document:
                if document.needs_pass and (self.password is None or not document.authenticate(self.password)):
                    raise PermissionError("The PDF requires a valid password.")
                page = document.load_page(self.page_index)
                zoom = self.zoom
                if self.fit_page:
                    zoom = min(
                        3.0,
                        self.available_width / page.rect.width,
                        self.available_height / page.rect.height,
                    )
                elif self.fit_width:
                    zoom = min(3.0, max(0.35, max(200, self.available_width) / page.rect.width))
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                page_count = document.page_count
                page_text = extract_page_text(page)
                rotation = page.rotation_matrix
            image = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            ).copy()
            painter = QPainter(image)
            painter.setPen(Qt.PenStyle.NoPen)
            color = QColor(self.highlight_color)
            color.setAlpha(105)
            painter.setBrush(color)
            for highlight in self.match.highlights:
                if highlight.page_index != self.page_index:
                    continue
                for x0, y0, x1, y1 in highlight.rectangles:
                    x0, y0, x1, y1 = fitz.Rect(x0, y0, x1, y1) * rotation
                    painter.drawRect(
                        int(x0 * zoom),
                        int(y0 * zoom),
                        max(1, int((x1 - x0) * zoom)),
                        max(1, int((y1 - y0) * zoom)),
                    )
            painter.end()
        except (fitz.FileDataError, fitz.EmptyFileError, OSError, ValueError):
            self.signals.failed.emit(self.request_id)
            return
        finally:
            self.password = None
        self.signals.finished.emit(self.request_id, image, page_count, zoom, page_text)


class PdfPreview(QWidget):
    def __init__(self, parent: QWidget | None = None, *, passwords: PdfPasswords | None = None) -> None:
        super().__init__(parent)
        self._passwords = passwords
        self._path: Path | None = None
        self._match: TextMatch | None = None
        self._page_index = 0
        self._page_count = 0
        self._zoom = 1.4
        self._fit_width = True
        self._fit_page = False
        self._language = "en"
        self._highlight_color = "#ffe128"
        self._request_id = 0
        self._page_ready = False
        self._pending_png: tuple[QImage, QByteArray] | None = None
        self._copy_attempts = 0
        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(self._write_page_clipboard)
        self._workers: dict[int, PreviewRenderWorker] = {}
        self._thread_pool = QThreadPool.globalInstance()
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._render)

        self.previous_button = SettingsButton("previous_page")
        self.next_button = SettingsButton("next_page")
        self.zoom_out_button = SettingsButton("zoom_out")
        self.zoom_in_button = SettingsButton("zoom_in")
        self.fit_button = SettingsButton("fit_width")
        self.fit_page_button = SettingsButton("fit_page")
        self.select_text_button = SettingsButton("select_text", checkable=True)
        self.select_text_button.setChecked(True)
        self.copy_page_button = SettingsButton("copy_page")
        self.page_label = QLabel()
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(SettingsButton.SPACING)
        toolbar.addWidget(self.previous_button)
        toolbar.addWidget(self.next_button)
        toolbar.addWidget(self.page_label)
        self.toolbar_separators = []

        def add_separator() -> None:
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.VLine)
            separator.setFixedWidth(13)
            separator.setFixedHeight(20)
            separator.setStyleSheet("border: 0; background: palette(mid); margin: 0 6px;")
            toolbar.addWidget(separator)
            self.toolbar_separators.append(separator)

        add_separator()
        toolbar.addStretch()
        toolbar.addWidget(self.select_text_button)
        toolbar.addWidget(self.copy_page_button)
        add_separator()
        toolbar.addWidget(self.zoom_out_button)
        toolbar.addWidget(self.zoom_in_button)
        toolbar.addWidget(self.fit_button)
        toolbar.addWidget(self.fit_page_button)

        self.image_label = SelectablePageLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self.scroll_area, 1)

        self.previous_button.clicked.connect(lambda: self._move_page(-1))
        self.next_button.clicked.connect(lambda: self._move_page(1))
        self.zoom_out_button.clicked.connect(lambda: self._change_zoom(0.8))
        self.zoom_in_button.clicked.connect(lambda: self._change_zoom(1.25))
        self.fit_button.clicked.connect(self._fit)
        self.fit_page_button.clicked.connect(self._fit_entire_page)
        self.select_text_button.toggled.connect(self.image_label.set_selection_mode)
        self.copy_page_button.clicked.connect(self._copy_page)
        self.image_label.selection_dragged.connect(
            lambda x, y: self.scroll_area.ensureVisible(x, y, 16, 16)
        )
        self.set_language(self._language)
        self.clear()

    def set_language(self, language: str) -> None:
        self._language = language
        self.previous_button.setToolTip(translate(language, "previous_page"))
        self.next_button.setToolTip(translate(language, "next_page"))
        self.zoom_out_button.setToolTip(translate(language, "zoom_out"))
        self.zoom_in_button.setToolTip(translate(language, "zoom_in"))
        self.fit_button.setToolTip(translate(language, "fit"))
        self.fit_page_button.setToolTip(translate(language, "fit_page"))
        self.copy_page_button.setToolTip(translate(language, "copy_page"))
        self.image_label.set_language(language)
        self._update_controls()
        self._update_page_label()

    def set_highlight_color(self, color: str) -> None:
        parsed = QColor(color)
        if not parsed.isValid():
            return
        self._highlight_color = parsed.name()
        if self._path is not None:
            self._render()

    def clear(self) -> None:
        self._page_ready = False
        self._copy_timer.stop()
        self._pending_png = None
        self._request_id += 1
        self._resize_timer.stop()
        self._path = None
        self._match = None
        self._page_index = 0
        self._page_count = 0
        self.image_label.clear()
        self.page_label.clear()
        self._update_controls()

    def show_match(self, path: str, match: TextMatch) -> None:
        self.clear()
        self._path = Path(path)
        self._match = match
        self._page_index = match.start_page
        self._fit_width = True
        self._fit_page = False
        self._update_controls()
        self._update_page_label()
        self._render()

    def _move_page(self, delta: int) -> None:
        target = self._page_index + delta
        if 0 <= target < self._page_count:
            self._page_index = target
            self._update_controls()
            self._update_page_label()
            self._render()

    def _change_zoom(self, factor: float) -> None:
        self._fit_width = False
        self._fit_page = False
        self._zoom = min(5.0, max(0.35, self._zoom * factor))
        self._render()

    def _fit(self) -> None:
        self._fit_width = True
        self._fit_page = False
        self._render()

    def _fit_entire_page(self) -> None:
        self._fit_width = False
        self._fit_page = True
        self._render()

    def _render(self) -> None:
        if self._path is None or self._match is None:
            return
        self._resize_timer.stop()
        self._page_ready = False
        self._request_id += 1
        request_id = self._request_id
        self.image_label.set_page_text(None)
        self._update_controls()
        viewport = self.scroll_area.viewport()
        available_width = max(1, viewport.width() - 24)
        available_height = max(1, viewport.height() - 24)
        worker = PreviewRenderWorker(
            request_id,
            self._path,
            self._page_index,
            self._match,
            self._zoom,
            self._fit_width,
            self._fit_page,
            available_width,
            available_height,
            self._highlight_color,
            password=self._passwords.get(self._path) if self._passwords is not None else None,
        )
        worker.signals.finished.connect(self._render_finished)
        worker.signals.failed.connect(self._render_failed)
        self._workers[request_id] = worker
        self._thread_pool.start(worker)

    def _render_finished(
        self, request_id: int, image: QImage, page_count: int, zoom: float, page_text: PageText
    ) -> None:
        self._workers.pop(request_id, None)
        if request_id != self._request_id:
            return
        self._page_count = page_count
        self._zoom = zoom
        self._page_ready = True
        self.image_label.setPixmap(QPixmap.fromImage(image))
        self.image_label.adjustSize()
        self.image_label.set_page_text(page_text, zoom)
        self._update_controls()
        self._update_page_label()

    def _render_failed(self, request_id: int) -> None:
        self._workers.pop(request_id, None)
        if request_id == self._request_id:
            self._page_ready = False
            self.image_label.clear()
            self._update_controls()

    def _copy_page(self) -> None:
        if not self._page_ready:
            return
        image = self.image_label.pixmap().toImage()
        png = QByteArray()
        buffer = QBuffer(png)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            return
        buffer.close()
        self._copy_timer.stop()
        self._pending_png = (image, png)
        self._copy_attempts = 0
        self._write_page_clipboard()

    def _write_page_clipboard(self) -> None:
        if self._pending_png is None:
            return
        image, png = self._pending_png
        mime = QMimeData()
        mime.setData("image/png", png)
        mime.setImageData(image)
        clipboard = QApplication.clipboard()
        clipboard.setMimeData(mime)
        self._copy_attempts += 1
        if sys.platform == "win32" and not clipboard.ownsClipboard() and self._copy_attempts < 10:
            self._copy_timer.start(100)
        else:
            self._pending_png = None

    def _update_page_label(self) -> None:
        if self._path is None:
            self.page_label.clear()
            return
        page = self._page_index + 1
        total: int | str = self._page_count if self._page_count else "…"
        self.page_label.setText(
            translate(self._language, "page", page=page, total=total)
        )

    def _update_controls(self) -> None:
        has_page = self._path is not None and self._match is not None
        self.copy_page_button.setEnabled(has_page and self._page_ready)
        self.select_text_button.setEnabled(has_page and self.image_label.has_text())
        key = "select_text" if not has_page or self.image_label.has_text() else "no_selectable_text"
        self.select_text_button.setToolTip(translate(self._language, key))
        self.previous_button.setEnabled(
            has_page and self._page_count > 0 and self._page_index > 0
        )
        self.next_button.setEnabled(
            has_page and self._page_index < self._page_count - 1
        )
        self.zoom_out_button.setEnabled(has_page)
        self.zoom_in_button.setEnabled(has_page)
        self.fit_button.setEnabled(has_page)
        self.fit_page_button.setEnabled(has_page)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if (self._fit_width or self._fit_page) and self._path is not None:
            self._resize_timer.start()
