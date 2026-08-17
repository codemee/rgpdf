# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rgpdf.i18n import translate
from rgpdf.models import TextMatch


class PreviewRenderSignals(QObject):
    finished = Signal(int, object, int, float)
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
        available_width: int,
        highlight_color: str,
    ) -> None:
        super().__init__()
        self.request_id = request_id
        self.path = path
        self.page_index = page_index
        self.match = match
        self.zoom = zoom
        self.fit_width = fit_width
        self.available_width = available_width
        self.highlight_color = highlight_color
        self.signals = PreviewRenderSignals()

    @Slot()
    def run(self) -> None:
        try:
            with fitz.open(self.path) as document:
                page = document.load_page(self.page_index)
                zoom = self.zoom
                if self.fit_width:
                    zoom = min(3.0, max(0.35, self.available_width / page.rect.width))
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                page_count = document.page_count
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
        self.signals.finished.emit(self.request_id, image, page_count, zoom)


class PdfPreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Path | None = None
        self._match: TextMatch | None = None
        self._matched_pages: list[int] = []
        self._matched_page_position = 0
        self._page_count = 0
        self._zoom = 1.4
        self._fit_width = True
        self._language = "en"
        self._highlight_color = "#ffe128"
        self._request_id = 0
        self._workers: dict[int, PreviewRenderWorker] = {}
        self._thread_pool = QThreadPool.globalInstance()
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._render)

        self.previous_button = QPushButton("‹")
        self.next_button = QPushButton("›")
        self.zoom_out_button = QPushButton("−")
        self.zoom_in_button = QPushButton("+")
        self.fit_button = QPushButton("Fit")
        self.page_label = QLabel()
        for button in (
            self.previous_button,
            self.next_button,
            self.zoom_out_button,
            self.zoom_in_button,
        ):
            button.setFixedWidth(34)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.addWidget(self.previous_button)
        toolbar.addWidget(self.next_button)
        toolbar.addWidget(self.page_label)
        toolbar.addStretch()
        toolbar.addWidget(self.zoom_out_button)
        toolbar.addWidget(self.zoom_in_button)
        toolbar.addWidget(self.fit_button)

        self.image_label = QLabel()
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
        self.clear()

    def set_language(self, language: str) -> None:
        self._language = language
        self.previous_button.setToolTip(translate(language, "previous_page"))
        self.next_button.setToolTip(translate(language, "next_page"))
        self.zoom_out_button.setToolTip(translate(language, "zoom_out"))
        self.zoom_in_button.setToolTip(translate(language, "zoom_in"))
        self.fit_button.setText(translate(language, "fit"))
        self._update_page_label()

    def set_highlight_color(self, color: str) -> None:
        parsed = QColor(color)
        if not parsed.isValid():
            return
        self._highlight_color = parsed.name()
        if self._path is not None:
            self._render()

    def clear(self) -> None:
        self._request_id += 1
        self._resize_timer.stop()
        self._path = None
        self._match = None
        self._matched_pages = []
        self._page_count = 0
        self.image_label.clear()
        self.page_label.clear()
        self._update_controls()

    def show_match(self, path: str, match: TextMatch) -> None:
        self.clear()
        self._path = Path(path)
        self._match = match
        self._matched_pages = [highlight.page_index for highlight in match.highlights]
        if not self._matched_pages:
            self._matched_pages = [match.start_page]
        self._matched_page_position = 0
        self._fit_width = True
        self._update_controls()
        self._update_page_label()
        self._render()

    def _move_page(self, delta: int) -> None:
        target = self._matched_page_position + delta
        if 0 <= target < len(self._matched_pages):
            self._matched_page_position = target
            self._render()

    def _change_zoom(self, factor: float) -> None:
        self._fit_width = False
        self._zoom = min(5.0, max(0.35, self._zoom * factor))
        self._render()

    def _fit(self) -> None:
        self._fit_width = True
        self._render()

    def _render(self) -> None:
        if self._path is None or self._match is None or not self._matched_pages:
            return
        self._request_id += 1
        request_id = self._request_id
        page_index = self._matched_pages[self._matched_page_position]
        available = max(200, self.scroll_area.viewport().width() - 24)
        worker = PreviewRenderWorker(
            request_id,
            self._path,
            page_index,
            self._match,
            self._zoom,
            self._fit_width,
            available,
            self._highlight_color,
        )
        worker.signals.finished.connect(self._render_finished)
        worker.signals.failed.connect(self._render_failed)
        self._workers[request_id] = worker
        self._thread_pool.start(worker)

    def _render_finished(
        self, request_id: int, image: QImage, page_count: int, zoom: float
    ) -> None:
        self._workers.pop(request_id, None)
        if request_id != self._request_id:
            return
        self._page_count = page_count
        self._zoom = zoom
        self.image_label.setPixmap(QPixmap.fromImage(image))
        self.image_label.adjustSize()
        self._update_page_label()

    def _render_failed(self, request_id: int) -> None:
        self._workers.pop(request_id, None)
        if request_id == self._request_id:
            self.image_label.clear()

    def _update_page_label(self) -> None:
        if not self._matched_pages:
            self.page_label.clear()
            return
        page = self._matched_pages[self._matched_page_position] + 1
        total: int | str = self._page_count if self._page_count else "…"
        self.page_label.setText(
            translate(self._language, "page", page=page, total=total)
        )

    def _update_controls(self) -> None:
        has_page = bool(self._matched_pages)
        self.previous_button.setEnabled(has_page and self._matched_page_position > 0)
        self.next_button.setEnabled(
            has_page and self._matched_page_position < len(self._matched_pages) - 1
        )
        self.zoom_out_button.setEnabled(has_page)
        self.zoom_in_button.setEnabled(has_page)
        self.fit_button.setEnabled(has_page)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if self._fit_width and self._path is not None:
            self._resize_timer.start()
