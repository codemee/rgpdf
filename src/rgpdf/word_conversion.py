# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Event


class WordConversionError(RuntimeError):
    """Raised when no available renderer can convert a Word document."""


class ConversionCancelled(RuntimeError):
    """Raised when cancellation is requested during conversion."""


Converter = tuple[str, Callable[[Path, Path, Event | None], None]]
CACHE_FORMAT_VERSION = "1"
CACHE_MAX_AGE_DAYS = 30
CACHE_MAX_BYTES = 500 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CacheCleanupResult:
    removed_files: int = 0
    removed_bytes: int = 0
    failed_files: int = 0


def _cache_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "rgpdf" / "cache" / "documents"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "rgpdf" / "documents"
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "rgpdf" / "documents"


def _libreoffice_executable() -> Path | None:
    command = shutil.which("soffice") or shutil.which("libreoffice")
    if command:
        return Path(command)

    candidates: list[Path] = []
    if sys.platform == "win32":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            if root := os.environ.get(variable):
                candidates.append(Path(root) / "LibreOffice" / "program" / "soffice.exe")
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
    return next((path for path in candidates if path.is_file()), None)


class _WordConverter:
    """Own a lazy Word application on the calling search thread."""

    def __init__(self) -> None:
        self.application = None
        self.pythoncom = None

    def __call__(self, source: Path, destination: Path, cancel_event: Event | None) -> None:
        if cancel_event and cancel_event.is_set():
            raise ConversionCancelled("Word conversion was cancelled.")
        if self.application is None:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            self.pythoncom = pythoncom
            try:
                self.application = win32com.client.DispatchEx("Word.Application")
                self.application.Visible = False
                self.application.DisplayAlerts = 0
                # Never run macros or update external links in searched documents.
                self.application.AutomationSecurity = 3
                self.application.Options.UpdateLinksAtOpen = False
            except Exception:
                self.close()
                raise
        document = None
        try:
            document = self.application.Documents.Open(
                FileName=str(source.resolve()),
                ConfirmConversions=False,
                ReadOnly=True,
                AddToRecentFiles=False,
                Revert=False,
                NoEncodingDialog=True,
            )
            if cancel_event and cancel_event.is_set():
                raise ConversionCancelled("Word conversion was cancelled.")
            document.ExportAsFixedFormat(
                OutputFileName=str(destination.resolve()),
                ExportFormat=17,  # wdExportFormatPDF
                OpenAfterExport=False,
            )
        finally:
            if document is not None:
                document.Close(SaveChanges=0)

    def close(self) -> None:
        application, self.application = self.application, None
        pythoncom, self.pythoncom = self.pythoncom, None
        try:
            if application is not None:
                application.Quit(SaveChanges=0)
        finally:
            if pythoncom is not None:
                pythoncom.CoUninitialize()


def _word_to_pdf(source: Path, destination: Path, cancel_event: Event | None) -> None:
    converter = _WordConverter()
    try:
        converter(source, destination, cancel_event)
    finally:
        converter.close()


@contextmanager
def word_conversion_session() -> Iterator[list[Converter]]:
    """Reuse one Word application per search, without starting it on cache hits."""
    word = _WordConverter()
    try:
        yield [
            (name, word if convert is _word_to_pdf else convert)
            for name, convert in available_converters()
        ]
    finally:
        word.close()


def _libreoffice_to_pdf(source: Path, destination: Path, cancel_event: Event | None) -> None:
    executable = _libreoffice_executable()
    if executable is None:
        raise WordConversionError("LibreOffice was not found.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lo-profile-", dir=destination.parent) as profile_name:
        profile_uri = Path(profile_name).resolve().as_uri()
        command = [
            str(executable),
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile_uri}",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(destination.parent),
            str(source.resolve()),
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
        )
        deadline = time.monotonic() + 120
        while process.poll() is None:
            if cancel_event and cancel_event.is_set():
                process.kill()
                process.communicate()
                raise ConversionCancelled("Word conversion was cancelled.")
            if time.monotonic() >= deadline:
                process.kill()
                process.communicate()
                raise WordConversionError("LibreOffice conversion timed out.")
            time.sleep(0.1)
        stdout, stderr = process.communicate()
        if process.returncode:
            detail = (stderr or stdout).strip()
            raise WordConversionError(detail or "LibreOffice conversion failed.")

        generated = destination.parent / f"{source.stem}.pdf"
        if not generated.is_file():
            raise WordConversionError("LibreOffice did not produce a PDF file.")
        if generated != destination:
            generated.replace(destination)


def available_converters() -> list[Converter]:
    converters: list[Converter] = []
    if sys.platform == "win32":
        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
        except ImportError:
            pass
        else:
            converters.append(("microsoft-word", _word_to_pdf))
    if _libreoffice_executable() is not None:
        converters.append(("libreoffice", _libreoffice_to_pdf))
    return converters


def _cache_path(source: Path, converter_name: str, cache_root: Path) -> Path:
    stat = source.stat()
    fingerprint = "\0".join(
        (
            CACHE_FORMAT_VERSION,
            converter_name,
            str(source.resolve()),
            str(stat.st_size),
            str(stat.st_mtime_ns),
        )
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    return cache_root / f"{digest}.pdf"


def cached_word_pdf(source: Path) -> Path | None:
    """Return a valid rendering without starting a converter or requiring one installed."""
    for name in ("microsoft-word", "libreoffice"):
        destination = _cache_path(source, name, _cache_root())
        if destination.is_file() and destination.stat().st_size:
            stat = destination.stat()
            os.utime(destination, (time.time(), stat.st_mtime))
            return destination
    return None


def _cache_files(root: Path) -> list[tuple[Path, os.stat_result]]:
    if not root.is_dir():
        return []
    files: list[tuple[Path, os.stat_result]] = []
    for path in root.glob("*.pdf"):
        try:
            if path.is_file():
                files.append((path, path.stat()))
        except OSError:
            continue
    return files


def _remove_cache_file(path: Path, size: int) -> CacheCleanupResult:
    try:
        path.unlink()
    except OSError:
        return CacheCleanupResult(failed_files=1)
    return CacheCleanupResult(removed_files=1, removed_bytes=size)


def _combine_cleanup_results(
    first: CacheCleanupResult, second: CacheCleanupResult
) -> CacheCleanupResult:
    return CacheCleanupResult(
        removed_files=first.removed_files + second.removed_files,
        removed_bytes=first.removed_bytes + second.removed_bytes,
        failed_files=first.failed_files + second.failed_files,
    )


def cleanup_word_cache(
    *,
    cache_root: Path | None = None,
    max_age_days: int = CACHE_MAX_AGE_DAYS,
    max_bytes: int = CACHE_MAX_BYTES,
    now: float | None = None,
) -> CacheCleanupResult:
    """Remove stale entries, then evict least-recently-used entries to the size cap."""
    root = cache_root or _cache_root()
    current_time = time.time() if now is None else now
    cutoff = current_time - max_age_days * 24 * 60 * 60
    result = CacheCleanupResult()
    remaining: list[tuple[Path, os.stat_result]] = []

    for path, stat in _cache_files(root):
        last_used = max(stat.st_atime, stat.st_mtime)
        if last_used < cutoff:
            result = _combine_cleanup_results(
                result, _remove_cache_file(path, stat.st_size)
            )
            if path.exists():
                remaining.append((path, stat))
        else:
            remaining.append((path, stat))

    total_bytes = sum(stat.st_size for _path, stat in remaining)
    for path, stat in sorted(remaining, key=lambda item: item[1].st_atime):
        if total_bytes <= max_bytes:
            break
        removed = _remove_cache_file(path, stat.st_size)
        result = _combine_cleanup_results(result, removed)
        if removed.removed_files:
            total_bytes -= stat.st_size
    return result


def clear_word_cache(*, cache_root: Path | None = None) -> CacheCleanupResult:
    """Remove all cached Word renderings that are not locked by another process."""
    root = cache_root or _cache_root()
    result = CacheCleanupResult()
    for path, stat in _cache_files(root):
        result = _combine_cleanup_results(
            result, _remove_cache_file(path, stat.st_size)
        )
    return result


def convert_word_to_pdf(
    source: Path,
    *,
    cancel_event: Event | None = None,
    cache_root: Path | None = None,
    converters: list[Converter] | None = None,
    conversion_started: Callable[[], None] | None = None,
) -> Path:
    """Convert *source* to a cached PDF using Word first, then LibreOffice."""
    candidates = available_converters() if converters is None else converters
    if not candidates:
        raise WordConversionError(
            "Microsoft Word or LibreOffice is required to search Word documents."
        )

    root = cache_root or _cache_root()
    root.mkdir(parents=True, exist_ok=True)
    cached_paths = [(_cache_path(source, name, root), name) for name, _ in candidates]
    for destination, _name in cached_paths:
        if destination.is_file() and destination.stat().st_size:
            stat = destination.stat()
            os.utime(destination, (time.time(), stat.st_mtime))
            return destination

    failures: list[str] = []
    for name, convert in candidates:
        if cancel_event and cancel_event.is_set():
            raise ConversionCancelled("Word conversion was cancelled.")
        destination = _cache_path(source, name, root)
        temporary = destination.with_suffix(".tmp.pdf")
        temporary.unlink(missing_ok=True)
        try:
            if conversion_started:
                conversion_started()
            convert(source, temporary, cancel_event)
            if not temporary.is_file() or not temporary.stat().st_size:
                raise WordConversionError(f"{name} produced an empty PDF file.")
            temporary.replace(destination)
            return destination
        except ConversionCancelled:
            temporary.unlink(missing_ok=True)
            raise
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            failures.append(f"{name}: {str(exc) or type(exc).__name__}")

    raise WordConversionError("; ".join(failures))
