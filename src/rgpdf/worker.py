from __future__ import annotations

from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from rgpdf.models import SearchOptions, SearchReport
from rgpdf.search import search_folder


class WorkerSignals(QObject):
    progress = Signal(int, int, str)
    document_found = Signal(object)
    match_found = Signal(object, object, object)
    finished = Signal(object)
    failed = Signal(str)


class SearchWorker(QRunnable):
    def __init__(self, options: SearchOptions) -> None:
        super().__init__()
        self.options = options
        self.signals = WorkerSignals()
        self.cancel_event = Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            report = search_folder(
                self.options,
                cancel_event=self.cancel_event,
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
