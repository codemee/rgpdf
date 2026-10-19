# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

"""Run CPU-heavy PDF search outside the UI and Word automation interpreter."""

from __future__ import annotations

from collections.abc import Callable
import multiprocessing
from multiprocessing.connection import Connection
from pathlib import Path
from threading import Event

from rgpdf.models import DocumentMatch, SearchOptions, TextMatch
from rgpdf.word_conversion import ConversionCancelled


class PdfSearchProcessError(ValueError):
    pass


def _serve(connection: Connection, options: SearchOptions) -> None:
    from rgpdf.search import compile_pattern, search_pdf

    try:
        compiled = compile_pattern(options)
        while True:
            request = connection.recv()
            if request is None:
                return
            path, source_path = request
            try:
                result = search_pdf(
                    path, options.root, options, compiled,
                    match_found=lambda match: connection.send(("match", match)),
                    source_path=source_path,
                )
                connection.send(("result", result))
            except Exception as exc:
                connection.send(("error", str(exc) or type(exc).__name__))
    except (EOFError, BrokenPipeError, OSError):
        return
    finally:
        connection.close()


class PdfSearchProcess:
    def __init__(self, options: SearchOptions, cancel_event: Event | None = None) -> None:
        self.options = options
        self.cancel_event = cancel_event
        self._process = None
        self._connection: Connection | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _start(self) -> None:
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(
            target=_serve, args=(child, self.options), name="rgpdf-pdf-search",
        )
        try:
            process.start()
        except BaseException:
            parent.close()
            child.close()
            raise
        child.close()
        self._process, self._connection = process, parent

    def search(
        self, path: Path, source_path: Path,
        match_found: Callable[[TextMatch], None] | None = None,
    ) -> DocumentMatch:
        if self.cancel_event and self.cancel_event.is_set():
            raise ConversionCancelled("Search was cancelled.")
        if self._process is None:
            self._start()
        try:
            self._connection.send((path, source_path))
            while True:
                if self.cancel_event and self.cancel_event.is_set():
                    self.close(terminate=True)
                    raise ConversionCancelled("Search was cancelled.")
                if not self._connection.poll(0.05):
                    if not self._process.is_alive():
                        raise PdfSearchProcessError("The PDF search process stopped unexpectedly.")
                    continue
                kind, payload = self._connection.recv()
                if kind == "match":
                    if match_found:
                        match_found(payload)
                elif kind == "result":
                    return payload
                elif kind == "error":
                    raise PdfSearchProcessError(payload)
        except (EOFError, BrokenPipeError, OSError) as exc:
            self.close(terminate=True)
            raise PdfSearchProcessError("The PDF search process disconnected.") from exc
        except PdfSearchProcessError:
            raise
        except BaseException:
            self.close(terminate=True)
            raise

    def close(self, *, terminate: bool = False) -> None:
        process, self._process = self._process, None
        connection, self._connection = self._connection, None
        if process is None:
            return
        try:
            if process.is_alive():
                if terminate:
                    process.terminate()
                else:
                    try:
                        connection.send(None)
                    except (EOFError, BrokenPipeError, OSError):
                        pass
            process.join(timeout=2)
            if process.is_alive():
                process.terminate()
                process.join()
        finally:
            connection.close()
            process.close()
