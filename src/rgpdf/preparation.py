# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

"""Folder-scoped Word preparation shared by browsing and searching."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, TimeoutError
import os
from pathlib import Path
from threading import Condition, Event, Thread
import time

from rgpdf.models import SearchOptions
from rgpdf.word_conversion import (
    CacheCleanupResult,
    ConversionCancelled,
    clear_word_cache,
    convert_word_to_pdf,
    word_conversion_session,
)


SourceKey = tuple[Path, int, int]


def _source_key(path: Path) -> SourceKey:
    path = path.resolve()
    stat = path.stat()
    return path, stat.st_size, stat.st_mtime_ns


class BackgroundWordPreparation:
    def __init__(
        self,
        *,
        converting: Callable[[str], None] = lambda name: None,
        busy_changed: Callable[[bool], None] = lambda busy: None,
    ) -> None:
        self._converting = converting
        self._busy_changed = busy_changed
        self._condition = Condition()
        self._stop = Event()
        self._thread: Thread | None = None
        self._revision = 0
        self._update: tuple[int, SearchOptions | None] | None = None
        self._pending: deque[SourceKey] = deque()
        self._results: dict[SourceKey, Future[Path]] = {}
        self._requested: dict[SourceKey, int] = {}
        self._busy = False

    def _start(self) -> None:
        if self._thread is None:
            self._thread = Thread(target=self._run, name="rgpdf-folder-preparation")
            self._thread.start()

    def update(self, options: SearchOptions | None) -> None:
        """Replace the pending selection; running conversion may finish and cache."""
        with self._condition:
            if self._stop.is_set():
                return
            self._revision += 1
            self._update = self._revision, options
            self._start()
            self._condition.notify_all()

    def get_pdf(self, path: Path, cancel_event: Event | None = None) -> Path:
        key = _source_key(path)
        with self._condition:
            if self._stop.is_set():
                raise ConversionCancelled("Background preparation was stopped.")
            future = self._results.get(key)
            if future is None or future.cancelled():
                future = Future()
                self._results[key] = future
                self._pending.appendleft(key)
            elif not future.done() and not future.running():
                self._pending.remove(key)
                self._pending.appendleft(key)
            self._requested[key] = self._requested.get(key, 0) + 1
            self._start()
            self._condition.notify_all()
        try:
            while not self._stop.is_set():
                if cancel_event and cancel_event.is_set():
                    raise ConversionCancelled("Search was cancelled.")
                try:
                    result = future.result(timeout=0.05)
                except TimeoutError:
                    if not future.done():
                        continue
                    result = future.result()
                if result.is_file() and _source_key(path) == key:
                    stat = result.stat()
                    os.utime(result, (time.time(), stat.st_mtime))
                    return result
                # A source change or cleared cache must never reuse stale output.
                with self._condition:
                    if self._results.get(key) is future:
                        self._results.pop(key, None)
                return self.get_pdf(path, cancel_event)
            raise ConversionCancelled("Background preparation was stopped.")
        finally:
            with self._condition:
                count = self._requested.get(key, 0) - 1
                if count > 0:
                    self._requested[key] = count
                else:
                    self._requested.pop(key, None)

    def clear_cache(self) -> CacheCleanupResult | None:
        """Clear only when idle, so no in-flight conversion can race deletion."""
        with self._condition:
            if self._busy or self._update is not None or self._pending or self._requested:
                return None
            result = clear_word_cache()
            self._results.clear()
            return result

    def close(self, *, wait: bool = False) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        thread = self._thread
        if wait and thread is not None:
            thread.join()

    def _selection(self, options: SearchOptions | None, revision: int) -> list[SourceKey]:
        from rgpdf.search import discover_documents

        if options is None or options.search_scope == "pdf" or not options.root.is_dir():
            return []
        keys = []
        for path in discover_documents(options.root, options.recursive, "word", options.stem_glob):
            with self._condition:
                if self._stop.is_set() or revision != self._revision:
                    break
            try:
                keys.append(_source_key(path))
            except OSError:
                continue
        return keys

    def _reconcile(self, revision: int, keys: list[SourceKey]) -> None:
        with self._condition:
            if revision != self._revision:
                return
            desired = set(keys) | self._requested.keys()
            for key, future in list(self._results.items()):
                if key not in desired and not future.running():
                    future.cancel()
                    self._results.pop(key, None)
            ordered = list(self._requested) + keys
            self._pending.clear()
            for key in dict.fromkeys(ordered):
                future = self._results.get(key)
                if future is None or future.cancelled() or (
                    future.done() and future.exception() is not None and key not in self._requested
                ):
                    future = Future()
                    self._results[key] = future
                if not future.done() and not future.running():
                    self._pending.append(key)

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                with self._condition:
                    while not self._stop.is_set() and not self._pending and self._update is None:
                        self._condition.wait()
                if self._stop.is_set():
                    break
                with self._condition:
                    self._busy = True
                self._busy_changed(True)
                try:
                    with word_conversion_session() as converters:
                        while not self._stop.is_set():
                            with self._condition:
                                update, self._update = self._update, None
                            if update is not None:
                                revision, options = update
                                self._reconcile(revision, self._selection(options, revision))
                                continue
                            with self._condition:
                                # Prefer any newly selected conditions over old queued work.
                                if self._update is not None:
                                    continue
                                if not self._pending:
                                    break
                                key = self._pending.popleft()
                                future = self._results[key]
                                if not future.set_running_or_notify_cancel():
                                    continue
                            started = False

                            def notify() -> None:
                                nonlocal started
                                started = True
                                if not self._stop.is_set():
                                    self._converting(key[0].name)

                            try:
                                pdf = convert_word_to_pdf(
                                    key[0], converters=converters, cancel_event=self._stop,
                                    conversion_started=notify,
                                )
                                future.set_result(pdf)
                            except Exception as exc:
                                future.set_exception(exc)
                            finally:
                                if started and not self._stop.is_set():
                                    self._converting("")
                finally:
                    with self._condition:
                        self._busy = False
                    if not self._stop.is_set():
                        self._busy_changed(False)
        except Exception as exc:
            with self._condition:
                for future in self._results.values():
                    if not future.done():
                        future.set_exception(exc)
                self._pending.clear()
        finally:
            with self._condition:
                self._busy = False
                for future in self._results.values():
                    if not future.done():
                        future.set_exception(ConversionCancelled("Preparation stopped."))
                self._thread = None
