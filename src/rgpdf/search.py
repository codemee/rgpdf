# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from threading import Event

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


class SearchInputError(ValueError):
    """Raised when a search pattern is invalid."""


class SearchTimedOut(RuntimeError):
    """Raised when a regular expression exceeds its per-document timeout."""


class NoSearchableText(RuntimeError):
    """Raised when a PDF has no usable text layer."""


def discover_pdfs(root: Path, recursive: bool) -> list[Path]:
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted(
        (path for path in iterator if path.is_file() and path.suffix.casefold() == ".pdf"),
        key=lambda path: str(path.relative_to(root)).casefold(),
    )


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


def extract_document(document: fitz.Document) -> ExtractedDocument:
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
    """Build a compact clause around a match, bounded by CJK or ASCII punctuation."""
    previous_marks = [text.rfind(mark, 0, start) for mark in CONTEXT_PUNCTUATION]
    previous = max(previous_marks, default=-1)
    if previous >= 0:
        left = previous + 1
        prefix = ""
    else:
        left = max(0, start - radius)
        prefix = "…" if left else ""

    following_marks = [
        position
        for mark in CONTEXT_PUNCTUATION
        if (position := text.find(mark, end)) >= 0
    ]
    if following_marks:
        right = min(following_marks) + 1
        suffix = ""
    else:
        right = min(len(text), end + radius)
        suffix = "…" if right < len(text) else ""

    return f"{prefix}{text[left:right].strip()}{suffix}"


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
) -> DocumentMatch:
    with fitz.open(path) as document:
        if document.needs_pass:
            raise PermissionError("The PDF is password protected.")
        extracted = extract_document(document)
    if not extracted.text.strip():
        raise NoSearchableText("The PDF has no searchable text layer.")
    matches = find_matches(
        extracted, compiled, options.regex_timeout_seconds, match_found=match_found
    )
    return DocumentMatch(path=path, relative_path=path.relative_to(root), matches=matches)


def search_folder(
    options: SearchOptions,
    *,
    cancel_event: Event | None = None,
    progress: Callable[[int, int, Path], None] | None = None,
    document_found: Callable[[DocumentMatch], None] | None = None,
    match_found: Callable[[Path, Path, TextMatch], None] | None = None,
    paths: Iterable[Path] | None = None,
) -> SearchReport:
    if not options.root.is_dir():
        raise SearchInputError("The selected folder does not exist.")
    compiled = compile_pattern(options)
    pdfs = list(paths) if paths is not None else discover_pdfs(options.root, options.recursive)
    report = SearchReport()
    for index, path in enumerate(pdfs, start=1):
        if cancel_event and cancel_event.is_set():
            report.cancelled = True
            break
        if progress:
            progress(index, len(pdfs), path)
        try:
            relative_path = path.relative_to(options.root)
            result = search_pdf(
                path,
                options.root,
                options,
                compiled,
                match_found=(
                    (lambda match, current=path, relative=relative_path: match_found(
                        current, relative, match
                    ))
                    if match_found
                    else None
                ),
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
            OSError,
            ValueError,
        ) as exc:
            report.warnings.append(SearchWarning(path, str(exc) or type(exc).__name__))
        report.scanned_files += 1
    return report
