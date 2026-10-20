# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from threading import Event
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from rgpdf.models import SearchOptions, SearchReport
from rgpdf.search import search_folder


class WorkerSignals(QObject):
    progress = Signal(int, int, str)
    screening = Signal(int, int, str)
    candidate_found = Signal(str, int)
    converting = Signal(str)
    document_found = Signal(object)
    match_found = Signal(object, object, object, object)
    finished = Signal(object)
    failed = Signal(str)


class SearchWorker(QRunnable):
    def __init__(
        self, options: SearchOptions,
        prepare_word: Callable[[Path, Event | None], Path] | None = None,
    ) -> None:
        super().__init__()
        self.options = options
        self.signals = WorkerSignals()
        self.cancel_event = Event()
        self.prepare_word = prepare_word

    def cancel(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            report = search_folder(
                self.options,
                cancel_event=self.cancel_event,
                prepare_word=self.prepare_word,
                isolate_pdf_search=True,
                conversion_started=lambda path: self.signals.converting.emit(path.name),
                conversion_finished=lambda: self.signals.converting.emit(""),
                screening=lambda current, total, path: self.signals.screening.emit(
                    current, total, path.name
                ),
                candidate_found=lambda path, count: self.signals.candidate_found.emit(path.name, count),
                progress=lambda current, total, path: self.signals.progress.emit(
                    current, total, path.name
                ),
                document_found=self.signals.document_found.emit,
                match_found=self.signals.match_found.emit,
            )
        except Exception as exc:  # Boundary between worker and UI thread.
            self.signals.failed.emit(str(exc) or type(exc).__name__)
            return
        self.signals.finished.emit(report)
