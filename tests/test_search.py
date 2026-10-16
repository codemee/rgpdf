from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
import pytest

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
