# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

"""Session-only PDF credentials, independent of settings and search results."""

from collections.abc import Callable
from pathlib import Path
from threading import Lock

import pymupdf as fitz


PasswordRequested = Callable[[Path, bool], str | None]
PasswordAccepted = Callable[[Path, str], None]


class PdfPasswordSkipped(PermissionError):
    pass


def unlock_pdf(document: fitz.Document, path: Path,
               requested: PasswordRequested | None = None,
               accepted: PasswordAccepted | None = None) -> None:
    if not document.needs_pass:
        return
    if requested is None:
        raise PermissionError("The PDF requires a password.")
    incorrect = False
    while document.is_encrypted:
        password = requested(path, incorrect)
        if password is None:
            raise PdfPasswordSkipped("Skipped password-protected PDF.")
        if document.authenticate(password):
            if accepted is not None:
                accepted(path, password)
            return
        incorrect = True


class PdfPasswords:
    """Keep successful credentials by source fingerprint in memory only."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._values: dict[tuple[Path, int, int], str] = {}
        self._closed = False

    @staticmethod
    def _key(path: Path) -> tuple[Path, int, int]:
        stat = path.stat()
        return path.resolve(), stat.st_size, stat.st_mtime_ns

    def get(self, path: Path) -> str | None:
        try:
            key = self._key(path)
        except OSError:
            return None
        with self._lock:
            return self._values.get(key)

    def remember(self, path: Path, password: str) -> None:
        try:
            key = self._key(path)
        except OSError:
            return
        with self._lock:
            if not self._closed:
                self._values[key] = password

    def forget(self, path: Path) -> None:
        resolved = path.resolve()
        with self._lock:
            self._values = {key: value for key, value in self._values.items() if key[0] != resolved}

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._values.clear()
