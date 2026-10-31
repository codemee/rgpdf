# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""One application-wide, FIFO Word renderer with reference-counted requests."""

from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from threading import Event, Lock, Thread

from PySide6.QtCore import QObject, Signal

from rgpdf.word_conversion import (
    ConversionCancelled, cached_word_pdf, convert_word_to_pdf, word_conversion_session,
)


@dataclass(eq=False)
class _Entry:
    key: tuple
    path: Path
    future: Future = field(default_factory=Future)
    cancel: Event = field(default_factory=Event)
    users: int = 0
    state: str = "queued"


class ConversionTicket:
    def __init__(self, service, entry):
        self.service, self.entry = service, entry
        self.future = entry.future
        self.released = False

    def release(self):
        with self.service._lock:
            if self.released:
                return
            self.released = True
            self.entry.users -= 1
            if not self.entry.users and not self.future.done():
                self.entry.cancel.set()
                if self.service._entries.get(self.entry.key) is self.entry:
                    self.service._entries.pop(self.entry.key)


class WordConversionService(QObject):
    changed = Signal(object, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = Lock()
        self._entries = {}
        self._queue = Queue()
        self._thread = None
        self._running = None
        self._closed = False

    @staticmethod
    def fingerprint(path):
        path = Path(path).resolve()
        stat = path.stat()
        return path, stat.st_size, stat.st_mtime_ns

    def submit(self, path):
        key = self.fingerprint(path)
        cached = cached_word_pdf(key[0])
        with self._lock:
            if self._closed:
                raise ConversionCancelled("Conversion service is closing.")
            entry = self._entries.get(key)
            if entry is None:
                entry = _Entry(key, key[0])
                if cached is not None:
                    entry.state = "ready"
                    entry.future.set_result(cached)
                else:
                    self._entries[key] = entry
                    self._queue.put(entry)
                    if self._thread is None:
                        self._thread = Thread(target=self._run, name="rgpdf-word-renderer")
                        self._thread.start()
            entry.users += 1
            return ConversionTicket(self, entry)

    def prepare(self, path, cancel_event=None):
        ticket = self.submit(path)
        try:
            while not ticket.future.done():
                if cancel_event is not None and cancel_event.is_set():
                    raise ConversionCancelled("Word conversion was cancelled.")
                Event().wait(0.05)
            if cancel_event is not None and cancel_event.is_set():
                raise ConversionCancelled("Word conversion was cancelled.")
            return ticket.future.result()
        finally:
            ticket.release()

    def state(self, path):
        resolved = Path(path).resolve()
        with self._lock:
            queued = [entry for entry in self._entries.values()
                      if entry.users and not entry.future.done()]
            if self._running is not None and self._running not in queued:
                queued.insert(0, self._running)
            for position, entry in enumerate(queued):
                if entry.path == resolved:
                    return entry.state, position
        return "confirming", 0

    def is_busy(self):
        with self._lock:
            return bool(self._entries or self._running)

    def _run(self):
        # COM and its lazy Word instance live exclusively on this thread.
        try:
            with word_conversion_session() as converters:
                while True:
                    entry = self._queue.get()
                    if entry is None:
                        break
                    try:
                        if entry.cancel.is_set():
                            raise ConversionCancelled("Unused conversion cancelled.")
                        with self._lock:
                            self._running = entry
                        entry.state = "converting"
                        self.changed.emit(entry.path, entry.state, 0)
                        result = cached_word_pdf(entry.path) or convert_word_to_pdf(
                            entry.path, converters=converters, cancel_event=entry.cancel,
                        )
                        if self.fingerprint(entry.path) != entry.key:
                            result.unlink(missing_ok=True)
                            raise OSError("Source changed during conversion; search again.")
                        entry.state = "ready"
                        entry.future.set_result(result)
                    except Exception as exc:
                        entry.state = "failed"
                        entry.future.set_exception(exc)
                    finally:
                        with self._lock:
                            self._running = None
                            if self._entries.get(entry.key) is entry:
                                self._entries.pop(entry.key)
                        self.changed.emit(entry.path, entry.state, 0)
        except Exception as exc:
            with self._lock:
                self._closed = True
                entries = list(self._entries.values())
                self._entries.clear()
            for entry in entries:
                if not entry.future.done():
                    entry.future.set_exception(exc)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for entry in self._entries.values():
                entry.cancel.set()
            if self._thread is not None:
                self._queue.put(None)

    def is_stopped(self):
        return self._thread is None or not self._thread.is_alive()
