from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
import pytest

from rgpdf.models import CharacterRef, ExtractedDocument, SearchOptions
from rgpdf.search import (
    _context,
    SearchInputError,
    compile_pattern,
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
        match_found=lambda path, relative, match: found_matches.append(
            (path.name, str(relative), match.matched_text)
        ),
    )
    assert [item.path.name for item in found_documents] == ["first.pdf", "second.pdf"]
    assert found_documents == report.documents
    assert found_matches == [
        ("first.pdf", "first.pdf", "find me"),
        ("first.pdf", "first.pdf", "find me"),
        ("second.pdf", "second.pdf", "find me"),
    ]
