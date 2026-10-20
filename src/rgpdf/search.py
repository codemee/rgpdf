# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

import pymupdf as fitz
import regex

from rgpdf.models import (
    CharacterRef,
    DocumentMatch,
    ExtractedDocument,
    PageHighlight,
    SearchOptions,
    SearchReport,
    SearchWarning,
    TextMatch,
)
from rgpdf.word_screening import word_may_match
from rgpdf.word_conversion import (
    ConversionCancelled,
    Converter,
    WordConversionError,
    convert_word_to_pdf,
    cached_word_pdf,
    word_conversion_session,
)


class SearchInputError(ValueError):
    """Raised when a search pattern is invalid."""


class SearchTimedOut(RuntimeError):
    """Raised when a regular expression exceeds its per-document timeout."""


class NoSearchableText(RuntimeError):
    """Raised when a PDF has no usable text layer."""


SEARCH_EXTENSIONS = {
    "pdf": frozenset({".pdf"}),
    "word": frozenset({".doc", ".docx"}),
    "all": frozenset({".pdf", ".doc", ".docx"}),
}


def discover_documents(
    root: Path, recursive: bool, search_scope: str = "pdf", stem_glob: str = ""
) -> list[Path]:
    try:
        extensions = SEARCH_EXTENSIONS[search_scope]
    except KeyError as exc:
        raise SearchInputError(f"Unsupported search scope: {search_scope}") from exc
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted(
        (
            path
            for path in iterator
            if path.is_file()
            and path.suffix.casefold() in extensions
            and _matches_stem(path, stem_glob)
        ),
        key=lambda path: str(path.relative_to(root)).casefold(),
    )


def _matches_stem(path: Path, stem_glob: str) -> bool:
    """Match the complete filename stem, consistently ignoring case on every OS."""
    return not stem_glob or fnmatchcase(path.stem.casefold(), stem_glob.casefold())


def discover_pdfs(root: Path, recursive: bool) -> list[Path]:
    """Backward-compatible PDF-only discovery helper."""
    return discover_documents(root, recursive, "pdf")


def compile_pattern(options: SearchOptions) -> regex.Pattern[str]:
    if not options.pattern:
        raise SearchInputError("Search pattern cannot be empty.")
    source = options.pattern if options.use_regex else regex.escape(options.pattern)
    flags = regex.VERSION1
    if not options.case_sensitive:
        flags |= regex.IGNORECASE | regex.FULLCASE
    try:
        return regex.compile(source, flags)
    except regex.error as exc:
        raise SearchInputError(str(exc)) from exc


def _append_text(
    text_parts: list[str],
    refs: list[CharacterRef],
    value: str,
    page_index: int,
    rectangle: tuple[float, float, float, float] | None,
) -> None:
    text_parts.append(value)
    refs.extend(CharacterRef(page_index, rectangle) for _ in value)


def _page_lines(
    page: fitz.Page,
) -> list[list[tuple[str, tuple[float, float, float, float] | None]]]:
    """Return reading-order lines with a precise rectangle for every character."""
    # RAWDICT otherwise includes decoded image payloads, which are irrelevant to
    # text search and can dominate extraction time in image-heavy PDFs.
    text_only_flags = fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES
    raw = page.get_text("rawdict", flags=text_only_flags, sort=True)
    lines: list[list[tuple[str, tuple[float, float, float, float] | None]]] = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for raw_line in block.get("lines", []):
            line: list[tuple[str, tuple[float, float, float, float] | None]] = []
            pending_space = False
            for span in raw_line.get("spans", []):
                for character in span.get("chars", []):
                    value = str(character.get("c", ""))
                    if not value:
                        continue
                    if value.isspace():
                        pending_space = bool(line)
                        continue
                    if pending_space:
                        line.append((" ", None))
                        pending_space = False
                    bbox = character.get("bbox")
                    rectangle = tuple(float(coordinate) for coordinate in bbox)
                    line.append((value, rectangle))
            if line:
                lines.append(line)
    return lines


def extract_document(document: fitz.Document, *, ignore_line_wraps: bool = False) -> ExtractedDocument:
    if ignore_line_wraps:
        from rgpdf.layout_text import extract_layout_document
        return extract_layout_document(document)
    text_parts: list[str] = []
    refs: list[CharacterRef] = []

    for page_index, page in enumerate(document):
        lines = _page_lines(page)
        for line_index, line in enumerate(lines):
            for value, rectangle in line:
                _append_text(text_parts, refs, value, page_index, rectangle)

            if line_index < len(lines) - 1:
                last_character = line[-1][0] if line else ""
                next_line = lines[line_index + 1]
                if last_character == "-" and next_line:
                    if text_parts and text_parts[-1].endswith("-"):
                        text_parts[-1] = text_parts[-1][:-1]
                        refs.pop()
                else:
                    _append_text(text_parts, refs, " ", page_index, None)

        if page_index < document.page_count - 1:
            separator_page = page_index if lines else page_index + 1
            _append_text(text_parts, refs, " ", separator_page, None)

    text = "".join(text_parts)
    if len(text) != len(refs):
        raise AssertionError("Text-to-coordinate mapping is inconsistent.")
    return ExtractedDocument(text=text, character_refs=tuple(refs), page_count=document.page_count)


CONTEXT_PUNCTUATION = "，。！？；：、,.!?;:"


def _context(text: str, start: int, end: int, radius: int = 55) -> str:
    """Build a single-line, bounded summary within punctuation/layout boundaries."""
    max_chars = 160
    radius = min(max(0, radius), (max_chars - 5) // 2)
    previous = max((text.rfind(mark, 0, start) for mark in CONTEXT_PUNCTUATION), default=-1)
    left_boundary = max(previous + 1, text.rfind("\n", 0, start) + 1)
    following = [position + 1 for mark in CONTEXT_PUNCTUATION
                 if (position := text.find(mark, end)) >= 0]
    newline = text.find("\n", end)
    right_boundary = min(following + ([newline] if newline >= 0 else []) + [len(text)])
    # Radius limits apply even when punctuation exists far away.
    left = max(left_boundary, start - radius)
    right = min(right_boundary, end + radius)
    prefix = "…" if left > left_boundary else ""
    suffix = "…" if right < right_boundary else ""
    before = regex.sub(r"\s+", " ", text[left:start])
    selected = regex.sub(r"\s+", " ", text[start:end])
    after = regex.sub(r"\s+", " ", text[end:right])
    budget = max_chars - len(prefix + before + after + suffix)
    if len(selected) > budget:
        half = (budget - 1) // 2
        selected = selected[:half] + "…" + selected[-(budget - half - 1):]
    return regex.sub(r"\s+", " ", prefix + before + selected + after + suffix).strip()


def _highlights(refs: Sequence[CharacterRef]) -> tuple[PageHighlight, ...]:
    by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    seen: dict[int, set[tuple[float, float, float, float]]] = {}
    for ref in refs:
        if ref.rectangle is None:
            continue
        page_seen = seen.setdefault(ref.page_index, set())
        if ref.rectangle not in page_seen:
            page_seen.add(ref.rectangle)
            by_page.setdefault(ref.page_index, []).append(ref.rectangle)
    return tuple(PageHighlight(page, tuple(rects)) for page, rects in sorted(by_page.items()))


def find_matches(
    extracted: ExtractedDocument,
    compiled: regex.Pattern[str],
    timeout_seconds: float,
    match_found: Callable[[TextMatch], None] | None = None,
) -> tuple[TextMatch, ...]:
    matches: list[TextMatch] = []
    try:
        iterator = compiled.finditer(extracted.text, timeout=timeout_seconds)
        for match in iterator:
            start, end = match.span()
            if start == end:
                continue
            refs = extracted.character_refs[start:end]
            visible_refs = [ref for ref in refs if ref.rectangle is not None]
            if not visible_refs:
                continue
            text_match = TextMatch(
                matched_text=match.group(),
                context=_context(extracted.text, start, end),
                start=start,
                end=end,
                start_page=min(ref.page_index for ref in visible_refs),
                end_page=max(ref.page_index for ref in visible_refs),
                highlights=_highlights(refs),
            )
            matches.append(text_match)
            if match_found:
                match_found(text_match)
    except TimeoutError as exc:
        raise SearchTimedOut("Regular expression timed out for this document.") from exc
    return tuple(matches)


def search_pdf(
    path: Path,
    root: Path,
    options: SearchOptions,
    compiled: regex.Pattern[str],
    match_found: Callable[[TextMatch], None] | None = None,
    *,
    source_path: Path | None = None,
) -> DocumentMatch:
    original_path = source_path or path
    with fitz.open(path) as document:
        if document.needs_pass:
            raise PermissionError("The PDF is password protected.")
        extracted = extract_document(document, ignore_line_wraps=options.ignore_line_wraps)
    if not extracted.text.strip():
        raise NoSearchableText("The PDF has no searchable text layer.")
    matches = find_matches(
        extracted, compiled, options.regex_timeout_seconds, match_found=match_found
    )
    return DocumentMatch(
        path=original_path,
        relative_path=original_path.relative_to(root),
        matches=matches,
        preview_path=path,
    )


def search_document(
    path: Path,
    root: Path,
    options: SearchOptions,
    compiled: regex.Pattern[str],
    *,
    cancel_event: Event | None = None,
    converters: list[Converter] | None = None,
    conversion_started: Callable[[Path], None] | None = None,
    match_found: Callable[[Path, TextMatch], None] | None = None,
) -> DocumentMatch:
    if path.suffix.casefold() == ".pdf":
        return search_pdf(
            path,
            root,
            options,
            compiled,
            (lambda match: match_found(path, match)) if match_found else None,
        )
    cached = cached_word_pdf(path)
    if cached is None and not word_may_match(path, options, cancel_event):
        return DocumentMatch(path, path.relative_to(root), ())
    preview_path = cached or convert_word_to_pdf(
        path,
        cancel_event=cancel_event,
        converters=converters,
        conversion_started=(lambda: conversion_started(path)) if conversion_started else None,
    )
    return search_pdf(
        preview_path,
        root,
        options,
        compiled,
        (lambda match: match_found(preview_path, match)) if match_found else None,
        source_path=path,
    )


@dataclass(frozen=True)
class _PreparedDocument:
    path: Path
    preview_path: Path | None = None
    error: Exception | None = None
    skipped: bool = False


class _PipelineCancellation:
    """Combine user cancellation with pipeline shutdown without changing user state."""

    def __init__(self, external: Event | None) -> None:
        self.external = external
        self.stopped = Event()

    def is_set(self) -> bool:
        return self.stopped.is_set() or bool(self.external and self.external.is_set())


@contextmanager
def _prepared_documents(
    paths: list[Path],
    cancel_event: Event | None,
    conversion_started: Callable[[Path], None] | None,
    conversion_finished: Callable[[], None] | None,
    options: SearchOptions,
    prepare_word: Callable[[Path, Event | None], Path] | None = None,
    screening: Callable[[int, int, Path], None] | None = None,
    candidate_found: Callable[[Path, int], None] | None = None,
) -> Iterator[Iterator[_PreparedDocument]]:
    # Separate screening, conversion, and PDF consumption. Neither producer waits
    # for PDF search, and ready PDFs bypass queued Word conversions.
    ready: Queue[_PreparedDocument | Exception | None] = Queue()
    candidates: Queue[Path | None] = Queue()
    cancellation = _PipelineCancellation(cancel_event)

    def screen() -> None:
        count = 0
        try:
            for index, path in enumerate(paths, start=1):
                if cancellation.is_set():
                    break
                if screening:
                    screening(index, len(paths), path)
                try:
                    if path.suffix.casefold() == ".pdf":
                        ready.put(_PreparedDocument(path, path))
                        continue
                    try:
                        cached = cached_word_pdf(path)
                    except OSError:
                        cached = None
                    if cached is not None:
                        ready.put(_PreparedDocument(path, cached))
                    elif word_may_match(path, options, cancellation):
                        count += 1
                        if candidate_found:
                            candidate_found(path, count)
                        candidates.put(path)
                    else:
                        ready.put(_PreparedDocument(path, skipped=True))
                except ConversionCancelled:
                    break
                except Exception as exc:
                    ready.put(_PreparedDocument(path, error=exc))
        except Exception as exc:
            ready.put(exc)
        finally:
            candidates.put(None)

    def prepare() -> None:
        try:
            # All COM initialization, exports, and cleanup stay on this thread.
            with word_conversion_session() as converters:
                while not cancellation.is_set():
                    try:
                        path = candidates.get(timeout=0.05)
                    except Empty:
                        continue
                    if path is None or cancellation.is_set():
                        break
                    started = False

                    def notify_conversion() -> None:
                        nonlocal started
                        started = True
                        if conversion_started:
                            conversion_started(path)

                    try:
                        if prepare_word is not None:
                            preview_path = prepare_word(path, cancellation)
                        else:
                            preview_path = convert_word_to_pdf(
                                path, cancel_event=cancellation, converters=converters,
                                conversion_started=notify_conversion,
                            )
                        ready.put(_PreparedDocument(path, preview_path))
                    except ConversionCancelled:
                        break
                    except Exception as exc:
                        ready.put(_PreparedDocument(path, error=exc))
                    finally:
                        if started and conversion_finished:
                            conversion_finished()
        except Exception as exc:
            ready.put(exc)
        finally:
            # Screening can still be yielding ready PDF or skipped entries if
            # initialization failed; the consumer must wait for both producers.
            screening_thread.join()
            ready.put(None)

    def receive() -> Iterator[_PreparedDocument]:
        while not cancellation.is_set():
            try:
                item = ready.get(timeout=0.05)
            except Empty:
                continue
            if item is None:
                return
            if isinstance(item, Exception):
                raise item
            yield item

    screening_thread = Thread(target=screen, name="rgpdf-word-screening")
    thread = Thread(target=prepare, name="rgpdf-conversion")
    screening_thread.start()
    thread.start()
    try:
        yield receive()
    finally:
        cancellation.stopped.set()
        screening_thread.join()
        thread.join()


def search_folder(
    options: SearchOptions,
    *,
    cancel_event: Event | None = None,
    progress: Callable[[int, int, Path], None] | None = None,
    document_found: Callable[[DocumentMatch], None] | None = None,
    match_found: Callable[[Path, Path, Path, TextMatch], None] | None = None,
    paths: Iterable[Path] | None = None,
    conversion_started: Callable[[Path], None] | None = None,
    conversion_finished: Callable[[], None] | None = None,
    prepare_word: Callable[[Path, Event | None], Path] | None = None,
    isolate_pdf_search: bool = False,
    screening: Callable[[int, int, Path], None] | None = None,
    candidate_found: Callable[[Path, int], None] | None = None,
) -> SearchReport:
    if not options.root.is_dir():
        raise SearchInputError("The selected folder does not exist.")
    compiled = compile_pattern(options)
    documents = (
        [path for path in paths if _matches_stem(path, options.stem_glob)]
        if paths is not None
        else discover_documents(
            options.root, options.recursive, options.search_scope, options.stem_glob
        )
    )
    report = SearchReport()

    from rgpdf.pdf_search_process import PdfSearchProcess

    process_context = PdfSearchProcess(options, cancel_event) if isolate_pdf_search else nullcontext()
    with process_context as pdf_process, _prepared_documents(
        documents, cancel_event, conversion_started, conversion_finished,
        options, prepare_word, screening, candidate_found,
    ) as prepared:
        for index, item in enumerate(prepared, start=1):
            path = item.path
            if cancel_event and cancel_event.is_set():
                report.cancelled = True
                break
            if progress:
                progress(index, len(documents), path)
            if item.skipped:
                report.scanned_files += 1
                continue
            try:
                if item.error is not None:
                    raise item.error
                relative_path = path.relative_to(options.root)
                preview_path = item.preview_path
                callback = (
                    lambda match, current=path, relative=relative_path, preview=preview_path: match_found(
                        current, relative, preview, match
                    )
                ) if match_found else None
                if pdf_process is not None:
                    result = pdf_process.search(preview_path, path, callback)
                else:
                    result = search_pdf(
                        preview_path, options.root, options, compiled,
                        match_found=callback, source_path=path,
                    )
                if result.matches:
                    report.documents.append(result)
                    if document_found:
                        document_found(result)
            except (
                fitz.FileDataError,
                fitz.EmptyFileError,
                PermissionError,
                SearchTimedOut,
                NoSearchableText,
                WordConversionError,
                OSError,
                ValueError,
            ) as exc:
                report.warnings.append(SearchWarning(path, str(exc) or type(exc).__name__))
            except ConversionCancelled:
                report.cancelled = True
                break
            report.scanned_files += 1
    if cancel_event and cancel_event.is_set():
        report.cancelled = True
    return report
