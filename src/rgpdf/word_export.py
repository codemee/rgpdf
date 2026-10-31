# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import nullcontext
from pathlib import Path
import shutil
import tempfile
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from rgpdf.search import discover_documents
from rgpdf.word_conversion import (
    ConversionCancelled, cached_word_pdf, convert_word_to_pdf, word_conversion_session,
)


@dataclass
class ExportReport:
    exported: int = 0
    skipped: int = 0
    errors: list[tuple[Path, str]] = field(default_factory=list)
    cancelled: bool = False


class ScanSignals(QObject):
    finished = Signal(int, object)


class WordFileScanWorker(QRunnable):
    def __init__(self, request: int, root: Path | None, recursive: bool, stem_glob: str):
        super().__init__()
        self.request, self.root = request, root
        self.recursive, self.stem_glob = recursive, stem_glob
        self.signals = ScanSignals()

    @Slot()
    def run(self):
        try:
            paths = discover_documents(self.root, self.recursive, "word", self.stem_glob) if self.root and self.root.is_dir() else []
            paths = [path for path in paths if not path.name.startswith("~$")]
        except OSError:
            paths = []
        self.signals.finished.emit(self.request, paths)


def duplicate_pdf_names(paths: list[Path]) -> bool:
    names = [path.with_suffix(".pdf").name.casefold() for path in paths]
    return len(names) != len(set(names))


def export_word_files(paths: list[Path], destination: Path, *, overwrite: bool = False,
                      cancel_event: Event | None = None, progress=None, prepare_word=None) -> ExportReport:
    if duplicate_pdf_names(paths):
        raise ValueError("Selected files have duplicate PDF filenames.")
    if not destination.is_dir():
        raise NotADirectoryError(str(destination))
    cancel = cancel_event if cancel_event is not None else Event()
    report = ExportReport()
    with (word_conversion_session() if prepare_word is None else nullcontext([])) as converters:
        for index, source in enumerate(paths):
            if cancel.is_set():
                report.cancelled = True
                break
            if progress:
                progress(index, len(paths), source.name)
            target = destination / source.with_suffix(".pdf").name
            temporary = None
            try:
                if target.exists() and not overwrite:
                    report.skipped += 1
                    continue
                cached = cached_word_pdf(source)
                if cached is None:
                    cached = (prepare_word(source, cancel) if prepare_word is not None
                              else convert_word_to_pdf(source, converters=converters, cancel_event=cancel))
                if cancel.is_set():
                    raise ConversionCancelled()
                # Stage a complete copy before publishing. Exclusive creation
                # also works on output volumes without hard-link support.
                with tempfile.NamedTemporaryFile(dir=destination, prefix=".rgpdf-", suffix=".tmp", delete=False) as handle:
                    temporary = Path(handle.name)
                shutil.copyfile(cached, temporary)
                if cancel.is_set():
                    raise ConversionCancelled()
                if overwrite:
                    temporary.replace(target)
                else:
                    try:
                        output = target.open("xb")
                    except FileExistsError:
                        report.skipped += 1
                        continue
                    try:
                        with output, temporary.open("rb") as content:
                            shutil.copyfileobj(content, output)
                    except Exception:
                        target.unlink(missing_ok=True)
                        raise
                report.exported += 1
            except ConversionCancelled:
                report.cancelled = True
                break
            except Exception as exc:
                report.errors.append((source, str(exc) or type(exc).__name__))
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    return report


class ExportSignals(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)


class WordExportWorker(QRunnable):
    def __init__(self, paths: list[Path], destination: Path, overwrite: bool, prepare_word=None):
        super().__init__()
        self.paths, self.destination, self.overwrite = paths, destination, overwrite
        self.cancel_event = Event()
        self.prepare_word = prepare_word
        self.signals = ExportSignals()

    def cancel(self):
        self.cancel_event.set()

    @Slot()
    def run(self):
        try:
            report = export_word_files(self.paths, self.destination, overwrite=self.overwrite,
                                       cancel_event=self.cancel_event, progress=self.signals.progress.emit,
                                       prepare_word=self.prepare_word)
        except Exception as exc:
            report = ExportReport(errors=[(self.destination, str(exc) or type(exc).__name__)])
        self.signals.finished.emit(report)
