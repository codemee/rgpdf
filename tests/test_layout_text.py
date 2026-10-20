import pymupdf as fitz
import pytest

from rgpdf.models import SearchOptions
from rgpdf.search import compile_pattern, extract_document, find_matches, search_folder


def _matches(document, query, enabled=True, regex=False):
    extracted = extract_document(document, ignore_line_wraps=enabled)
    assert len(extracted.text) == len(extracted.character_refs)
    options = SearchOptions('.', query, use_regex=regex)
    return find_matches(extracted, compile_pattern(options), 1.0)


def test_cjk_wrap_is_optional_and_highlights_both_original_lines():
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), '循環\n緩衝區', fontname='china-t', fontsize=12)
        assert not _matches(document, '循環緩衝區', enabled=False)
        matches = _matches(document, '循環緩衝區')
        assert len(matches) == 1
        boxes = matches[0].highlights[0].rectangles
        assert len(boxes) == 5
        assert len({round(box[1], 1) for box in boxes}) == 2
        assert len(_matches(document, r'循環\s*緩衝區', regex=True)) == 1


@pytest.mark.parametrize('text,query', [('buffer\nsize', 'buffer size'),
                                         ('inter-\nnational', 'international')])
def test_latin_wraps_and_hyphenation(text, query):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), text, fontsize=12)
        assert len(_matches(document, query)) == 1


def test_real_spaces_are_preserved_within_and_at_line_edges():
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), '循環 緩衝區', fontname='china-t', fontsize=12)
        assert not _matches(document, '循環緩衝區')
        assert len(_matches(document, '循環 緩衝區')) == 1
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), '循環 \n緩衝區', fontname='china-t', fontsize=12)
        assert not _matches(document, '循環緩衝區')


def test_separate_paragraphs_columns_and_pages_do_not_join():
    for positions in (((72, 72), (72, 170)), ((72, 72), (300, 90))):
        with fitz.open() as document:
            page = document.new_page()
            for point, value in zip(positions, ('循環', '緩衝區')):
                page.insert_text(point, value, fontname='china-t', fontsize=12)
            assert not _matches(document, '循環緩衝區')
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), '循環', fontname='china-t', fontsize=12)
        document.new_page().insert_text((72, 72), '緩衝區', fontname='china-t', fontsize=12)
        assert not _matches(document, '循環緩衝區')


def test_distinct_table_cells_do_not_join():
    with fitz.open() as document:
        page = document.new_page()
        # Four cells; first-column rows could otherwise look like soft wraps.
        for x in (60, 180, 300):
            page.draw_line((x, 50), (x, 90))
        for y in (50, 70, 90):
            page.draw_line((60, y), (300, y))
        for point, value in (((70, 65), '循環'), ((70, 85), '緩衝區'),
                             ((190, 65), '欄位甲'), ((190, 85), '欄位乙')):
            page.insert_text(point, value, fontname='china-t', fontsize=12)
        assert page.find_tables().tables
        assert not _matches(document, '循環緩衝區')


def test_page_boundaries_retain_existing_space_semantics():
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), 'alpha', fontsize=12)
        document.new_page().insert_text((72, 72), 'beta', fontsize=12)
        assert len(_matches(document, 'alpha beta')) == 1


def test_subprocess_search_carries_wrap_option_and_original_rectangles(tmp_path):
    path = tmp_path / 'sample.pdf'
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), '循環\n緩衝區', fontname='china-t', fontsize=12)
        document.save(path)
    options = SearchOptions(tmp_path, '循環緩衝區', ignore_line_wraps=True)
    report = search_folder(options, isolate_pdf_search=True)
    assert not report.warnings and len(report.documents) == 1
    assert len(report.documents[0].matches[0].highlights[0].rectangles) == 5
