from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
from threading import Event, get_ident

import pymupdf as fitz
import pytest
from rgpdf.word_conversion import ConversionCancelled, WordConversionError

from rgpdf.models import CharacterRef, ExtractedDocument, SearchOptions
from rgpdf.search import (
    _context,
    SearchInputError,
    compile_pattern,
    discover_documents,
    discover_pdfs,
    extract_document,
    find_matches,
    search_folder,
)


def _write_pdf(path: Path, pages: list[list[tuple[tuple[float, float], str]]]) -> None:
    document = fitz.open()
    for lines in pages:
        page = document.new_page()
        for point, text in lines:
            page.insert_text(point, text, fontsize=12)
    document.save(path)
    document.close()


def test_compile_plain_text_escapes_regex_characters(tmp_path: Path) -> None:
    options = SearchOptions(root=tmp_path, pattern="a.b", use_regex=False)
    pattern = compile_pattern(options)
    assert pattern.search("A.B")
    assert not pattern.search("axb")


def test_context_is_bounded_by_nearest_chinese_punctuation() -> None:
    text = "上一句。這裡包含命中項目，後面還有內容；下一段。"
    start = text.index("命中")
    end = start + len("命中")
    assert _context(text, start, end) == "這裡包含命中項目，"


def test_context_is_bounded_by_nearest_english_punctuation() -> None:
    text = "Previous sentence. This contains the match, followed by more; Next sentence."
    start = text.index("match")
    end = start + len("match")
    assert _context(text, start, end) == "This contains the match,"


def test_context_uses_limited_fallback_without_chinese_punctuation() -> None:
    text = "a" * 80 + "match" + "b" * 80
    start = text.index("match")
    result = _context(text, start, start + len("match"), radius=10)
    assert result == "…aaaaaaaaaamatchbbbbbbbbbb…"


def test_compile_regex_and_case_sensitivity(tmp_path: Path) -> None:
    insensitive = compile_pattern(SearchOptions(tmp_path, r"foo\d+", use_regex=True))
    sensitive = compile_pattern(
        SearchOptions(tmp_path, r"foo\d+", use_regex=True, case_sensitive=True)
    )
    assert insensitive.search("FOO12")
    assert not sensitive.search("FOO12")


def test_invalid_and_empty_patterns(tmp_path: Path) -> None:
    with pytest.raises(SearchInputError):
        compile_pattern(SearchOptions(tmp_path, ""))
    with pytest.raises(SearchInputError):
        compile_pattern(SearchOptions(tmp_path, "(", use_regex=True))


def test_discover_pdfs_honors_recursive_flag(tmp_path: Path) -> None:
    (tmp_path / "top.PDF").touch()
    (tmp_path / "ignore.txt").touch()
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "inside.pdf").touch()
    assert discover_pdfs(tmp_path, recursive=False) == [tmp_path / "top.PDF"]
    assert discover_pdfs(tmp_path, recursive=True) == [
        nested / "inside.pdf",
        tmp_path / "top.PDF",
    ]


def test_discover_documents_filters_pdf_word_or_both(tmp_path: Path) -> None:
    for name in ("one.pdf", "two.docx", "three.DOC", "ignore.docm", "ignore.txt"):
        (tmp_path / name).touch()
    assert [path.name for path in discover_documents(tmp_path, False, "pdf")] == [
        "one.pdf"
    ]
    assert [path.name for path in discover_documents(tmp_path, False, "word")] == [
        "three.DOC",
        "two.docx",
    ]
    assert [path.name for path in discover_documents(tmp_path, False, "all")] == [
        "one.pdf",
        "three.DOC",
        "two.docx",
    ]


@pytest.mark.parametrize(
    "stem_glob,expected",
    [
        ("", ["ch01.notes.pdf", "ch01.pdf", "ch02.DOCX", "ch1.doc", "ch2.pdf"]),
        ("*", ["ch01.notes.pdf", "ch01.pdf", "ch02.DOCX", "ch1.doc", "ch2.pdf"]),
        ("ch0*", ["ch01.notes.pdf", "ch01.pdf", "ch02.DOCX"]),
        ("CH0?", ["ch01.pdf", "ch02.DOCX"]),
        ("ch0[12]", ["ch01.pdf", "ch02.DOCX"]),
        ("ch[!0]", ["ch1.doc", "ch2.pdf"]),
        ("ch01", ["ch01.pdf"]),
        ("ch01.pdf", []),
    ],
)
def test_stem_glob_matches_whole_stem_without_extension(tmp_path, stem_glob, expected):
    for name in ("ch01.pdf", "ch02.DOCX", "ch1.doc", "ch2.pdf", "ch01.notes.pdf", "ch03.txt"):
        (tmp_path / name).touch()
    assert [p.name for p in discover_documents(tmp_path, False, "all", stem_glob)] == expected


def test_stem_glob_respects_scope_and_recursion_without_matching_parent_folder(tmp_path):
    (tmp_path / "ch01.pdf").touch()
    (tmp_path / "ch02.docx").touch()
    nested = tmp_path / "ch0-folder"
    nested.mkdir()
    (nested / "ch03.pdf").touch()
    (nested / "ch1.pdf").touch()
    assert discover_documents(tmp_path, False, "pdf", "ch0*") == [tmp_path / "ch01.pdf"]
    assert discover_documents(tmp_path, True, "pdf", "ch0*") == [
        nested / "ch03.pdf", tmp_path / "ch01.pdf"
    ]
    assert discover_documents(tmp_path, True, "word", "ch0*") == [tmp_path / "ch02.docx"]


@pytest.mark.parametrize("explicit_paths", [False, True])
def test_stem_glob_filters_before_reading_or_converting_documents(tmp_path, monkeypatch, explicit_paths):
    root = tmp_path / "documents"
    root.mkdir()
    _write_pdf(root / "ch01.pdf", [[((72, 72), "needle")]])
    (root / "ch02.docx").touch()
    (root / "ch1.doc").touch()
    (root / "ch2.pdf").write_bytes(b"invalid PDF that should never be read")
    converted = tmp_path / "converted.pdf"
    _write_pdf(converted, [[((72, 72), "needle")]])
    conversions = []

    def convert(path, **kwargs):
        conversions.append(path.name)
        return converted

    monkeypatch.setattr("rgpdf.search.convert_word_to_pdf", convert)
    progress = []
    report = search_folder(
        SearchOptions(root, "needle", search_scope="all", stem_glob="ch0*"),
        paths=sorted(root.iterdir()) if explicit_paths else None,
        progress=lambda current, total, path: progress.append((current, total, path.name)),
    )
    assert conversions == ["ch02.docx"]
    assert report.scanned_files == 2
    assert not report.warnings
    assert [doc.path.name for doc in report.documents] == ["ch01.pdf", "ch02.docx"]
    assert progress == [(1, 2, "ch01.pdf"), (2, 2, "ch02.docx")]


def test_find_matches_reports_cross_page_highlights(tmp_path: Path) -> None:
    refs = tuple(
        [CharacterRef(0, (1, 1, 2, 2)) for _ in "alpha"]
        + [CharacterRef(0, None)]
        + [CharacterRef(1, (3, 3, 4, 4)) for _ in "beta"]
    )
    extracted = ExtractedDocument("alpha beta", refs, 2)
    compiled = compile_pattern(SearchOptions(tmp_path, r"alpha\s+beta", use_regex=True))
    matches = find_matches(extracted, compiled, 1.0)
    assert len(matches) == 1
    assert matches[0].start_page == 0
    assert matches[0].end_page == 1
    assert [highlight.page_index for highlight in matches[0].highlights] == [0, 1]


def test_extract_document_merges_line_end_hyphen(tmp_path: Path) -> None:
    path = tmp_path / "hyphen.pdf"
    _write_pdf(path, [[((72, 72), "inter-"), ((72, 92), "national search")]])
    with fitz.open(path) as document:
        extracted = extract_document(document)
    assert "international search" in extracted.text
    assert len(extracted.text) == len(extracted.character_refs)


def test_search_folder_finds_plain_text_across_pages(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    _write_pdf(path, [[((72, 72), "alpha")], [((72, 72), "beta")]])
    report = search_folder(SearchOptions(tmp_path, "alpha beta"))
    assert report.scanned_files == 1
    assert len(report.documents) == 1
    assert len(report.documents[0].matches) == 1
    assert report.documents[0].matches[0].start_page == 0
    assert report.documents[0].matches[0].end_page == 1


def test_partial_word_match_uses_only_matched_character_boxes(tmp_path: Path) -> None:
    path = tmp_path / "substring.pdf"
    _write_pdf(path, [[((72, 72), "example")]])
    report = search_folder(SearchOptions(tmp_path, "amp", case_sensitive=True))
    highlight = report.documents[0].matches[0].highlights[0]
    assert len(highlight.rectangles) == 3
    assert highlight.rectangles[0][0] > 72
    assert highlight.rectangles[-1][2] < 115


def test_search_folder_isolates_bad_pdf(tmp_path: Path) -> None:
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    report = search_folder(SearchOptions(tmp_path, "anything"))
    assert report.scanned_files == 1
    assert not report.documents
    assert len(report.warnings) == 1


def test_search_folder_reports_pdf_without_text_layer(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()
    report = search_folder(SearchOptions(tmp_path, "anything"))
    assert report.scanned_files == 1
    assert not report.documents
    assert "no searchable text layer" in report.warnings[0].message


def test_search_folder_reports_matching_documents_incrementally(tmp_path: Path) -> None:
    _write_pdf(tmp_path / "first.pdf", [[((72, 72), "find me and find me")]])
    _write_pdf(tmp_path / "second.pdf", [[((72, 72), "find me too")]])
    found_documents = []
    found_matches = []
    report = search_folder(
        SearchOptions(tmp_path, "find me"),
        document_found=found_documents.append,
        match_found=lambda path, relative, preview, match: found_matches.append(
            (path.name, str(relative), preview.name, match.matched_text)
        ),
    )
    assert [item.path.name for item in found_documents] == ["first.pdf", "second.pdf"]
    assert found_documents == report.documents
    assert found_matches == [
        ("first.pdf", "first.pdf", "first.pdf", "find me"),
        ("first.pdf", "first.pdf", "first.pdf", "find me"),
        ("second.pdf", "second.pdf", "second.pdf", "find me"),
    ]


def test_search_word_uses_converted_pdf_for_matching_and_preview(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "sample.docx"
    source.touch()
    converted = tmp_path / "converted.pdf"
    _write_pdf(converted, [[((72, 72), "find this")]])
    monkeypatch.setattr("rgpdf.search.convert_word_to_pdf", lambda *args, **kwargs: converted)

    report = search_folder(SearchOptions(tmp_path, "find", search_scope="word"))

    assert report.scanned_files == 1
    assert report.documents[0].path == source
    assert report.documents[0].relative_path == Path("sample.docx")
    assert report.documents[0].preview_path == converted
    assert report.documents[0].matches[0].matched_text == "find"


def test_next_word_conversion_overlaps_current_search(tmp_path, monkeypatch):
    sources = [tmp_path / "first.docx", tmp_path / "second.docx"]
    for source in sources:
        source.touch()
    converted = []
    for index in range(2):
        path = tmp_path / f"rendered-{index}.pdf"
        _write_pdf(path, [[((72, 72), "needle")]])
        converted.append(path)
    searching_first, converting_second, release_second = Event(), Event(), Event()
    session_threads = []

    @contextmanager
    def session():
        session_threads.append(get_ident())
        try:
            yield []
        finally:
            session_threads.append(get_ident())

    def convert(path, **kwargs):
        assert get_ident() == session_threads[0]
        if path == sources[1]:
            assert searching_first.wait(3)
            converting_second.set()
            assert release_second.wait(3)
        return converted[sources.index(path)]

    import rgpdf.search as search
    original = search.search_pdf

    def search_pdf(path, *args, **kwargs):
        if path == converted[0]:
            searching_first.set()
            try:
                assert converting_second.wait(3), "conversion must start before search finishes"
                return original(path, *args, **kwargs)
            finally:
                release_second.set()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(search, "word_conversion_session", session)
    monkeypatch.setattr(search, "convert_word_to_pdf", convert)
    monkeypatch.setattr(search, "search_pdf", search_pdf)
    found = []
    report = search_folder(
        SearchOptions(tmp_path, "needle"), paths=sources,
        match_found=lambda source, relative, preview, match: found.append((source, preview)),
    )
    assert not report.warnings
    assert report.scanned_files == 2
    assert [doc.path for doc in report.documents] == sources
    assert found == list(zip(sources, converted))
    assert len(session_threads) == 2 and session_threads[0] == session_threads[1]
    assert session_threads[0] != get_ident()


def test_pipeline_cancel_stops_conversion_and_closes_its_session(tmp_path, monkeypatch):
    sources = [tmp_path / f"file-{i}.docx" for i in range(3)]
    for source in sources:
        source.touch()
    pdf = tmp_path / "preview.pdf"
    _write_pdf(pdf, [[((72, 72), "needle")]])
    cancelled, second_started, closed = Event(), Event(), Event()
    converted = []

    @contextmanager
    def session():
        try:
            yield []
        finally:
            closed.set()

    def convert(path, **kwargs):
        converted.append(path)
        if path == sources[1]:
            second_started.set()
            assert cancelled.wait(3)
            assert kwargs["cancel_event"].is_set()
            raise ConversionCancelled()
        return pdf

    import rgpdf.search as search
    original = search.search_pdf

    def search_pdf(*args, **kwargs):
        assert second_started.wait(3)
        cancelled.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(search, "word_conversion_session", session)
    monkeypatch.setattr(search, "convert_word_to_pdf", convert)
    monkeypatch.setattr(search, "search_pdf", search_pdf)
    report = search_folder(SearchOptions(tmp_path, "needle"), paths=sources, cancel_event=cancelled)
    assert report.cancelled and not report.warnings
    assert report.scanned_files == 1
    assert converted == sources[:2]
    assert closed.is_set()


def test_pipeline_conversion_failure_does_not_block_following_pdf(tmp_path, monkeypatch):
    source = tmp_path / "broken.docx"
    source.touch()
    pdf = tmp_path / "good.pdf"
    _write_pdf(pdf, [[((72, 72), "needle")]])

    def fail(*args, **kwargs):
        raise WordConversionError("conversion failed")

    monkeypatch.setattr("rgpdf.search.convert_word_to_pdf", fail)
    report = search_folder(SearchOptions(tmp_path, "needle"), paths=[source, pdf])
    assert report.scanned_files == 2
    assert [doc.path for doc in report.documents] == [pdf]
    assert len(report.warnings) == 1 and report.warnings[0].path == source


@pytest.mark.parametrize("fail_first_search", [False, True])
def test_conversion_finishes_independently_while_first_search_waits(
    tmp_path, monkeypatch, fail_first_search
):
    sources = [tmp_path / f"file-{i}.docx" for i in range(8)]
    first_search_started, all_converted, closed = Event(), Event(), Event()
    converted = []
    pdf = tmp_path / "preview.pdf"
    _write_pdf(pdf, [[((72, 72), "needle")]])

    @contextmanager
    def session():
        try:
            yield []
        finally:
            closed.set()

    def convert(path, **kwargs):
        if path == sources[1]:
            assert first_search_started.wait(3)
        converted.append(path)
        if len(converted) == len(sources):
            all_converted.set()
        return pdf

    import rgpdf.search as search
    original = search.search_pdf

    def search_pdf(*args, **kwargs):
        first_search_started.set()
        assert all_converted.wait(3), "conversion must finish without waiting for the first search"
        if fail_first_search:
            raise RuntimeError("unexpected search failure")
        return original(*args, **kwargs)

    monkeypatch.setattr("rgpdf.search.word_conversion_session", session)
    monkeypatch.setattr("rgpdf.search.convert_word_to_pdf", convert)
    monkeypatch.setattr("rgpdf.search.search_pdf", search_pdf)
    if fail_first_search:
        with pytest.raises(RuntimeError, match="unexpected search failure"):
            search_folder(SearchOptions(tmp_path, "needle"), paths=sources)
    else:
        report = search_folder(SearchOptions(tmp_path, "needle"), paths=sources)
        assert not report.warnings
        assert report.scanned_files == len(sources)
        assert [doc.path for doc in report.documents] == sources
    assert closed.is_set()
    assert converted == sources
