from threading import Event
from xml.sax.saxutils import escape
from zipfile import ZipFile

import pytest

from rgpdf.models import SearchOptions
from rgpdf.word_screening import word_may_match
from rgpdf.word_conversion import ConversionCancelled


def docx(path, text="", extra="", parts=None):
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body><w:p><w:r><w:t>{escape(text)}</w:t></w:r>{extra}</w:p></w:body>'
            '</w:document>'
        ))
        for name, content in (parts or {}).items():
            archive.writestr(name, content)
    return path


def test_literal_screening_rules_out_nonmatch_and_keeps_candidates(tmp_path):
    source = docx(tmp_path / "a.docx", "hello world")
    assert not word_may_match(source, SearchOptions(tmp_path, "absent"))
    assert word_may_match(source, SearchOptions(tmp_path, "WORLD"))
    # Individual letters scattered through a document are not a phrase hit.
    assert not word_may_match(source, SearchOptions(tmp_path, "word hello"))
    assert not word_may_match(source, SearchOptions(tmp_path, "helloooo"))


def test_screening_handles_runs_hyphenation_casefold_and_headers(tmp_path):
    source = docx(tmp_path / "a.docx", "inter-", '<w:r><w:t>national Straße</w:t></w:r>', {
        "word/header1.xml": '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:r><w:t>UniqueHeader</w:t></w:r></w:hdr>',
    })
    for query in ("international", "STRASSE", "uniqueheader"):
        assert word_may_match(source, SearchOptions(tmp_path, query))


def test_screening_is_permissive_about_unicode_variants(tmp_path):
    source = docx(tmp_path / "a.docx", "ı İstanbul ﬃ é")
    for query in ("I", "istanbul", "ffi", "é"):
        assert word_may_match(source, SearchOptions(tmp_path, query))


def test_literal_pattern_still_screens_when_regex_is_enabled(tmp_path):
    source = docx(tmp_path / "a.docx", "these words do not contain the query")
    assert not word_may_match(source, SearchOptions(tmp_path, "循環緩衝區", use_regex=True))
    source = docx(source, "循環緩衝區")
    assert word_may_match(source, SearchOptions(tmp_path, "循環緩衝區", use_regex=True))


@pytest.mark.parametrize("pattern", ["a.b", "^a", "a$", "a*", "a+", "a?", "[ab]", "a{2}", r"\w", "a|b", "(a)"])
def test_actual_regex_operators_bypass_screening(tmp_path, pattern):
    source = docx(tmp_path / "a.docx", "unrelated")
    assert word_may_match(source, SearchOptions(tmp_path, pattern, use_regex=True))


def test_images_numbering_and_unused_styles_do_not_force_conversion(tmp_path):
    source = docx(tmp_path / "a.docx", "循環和緩衝區是分開的字詞", (
        '<w:pPr><w:numPr/></w:pPr><w:r><w:drawing/><w:pict/><w:sym w:char="F0B7"/></w:r>'
    ), {"word/styles.xml": (
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style><w:caps/><w:smallCaps/><w:numPr/><w:t>循環緩衝區</w:t></w:style></w:styles>'
    )})
    # Every character exists, but the actual phrase does not.
    assert not word_may_match(source, SearchOptions(tmp_path, "循環緩衝區", use_regex=True))


def test_numbering_can_still_supply_generated_counters(tmp_path):
    source = docx(tmp_path / "a.docx", "paragraph", '<w:pPr><w:numPr/></w:pPr>')
    assert word_may_match(source, SearchOptions(tmp_path, "123"))
    assert not word_may_match(source, SearchOptions(tmp_path, "unrelated phrase"))


def test_drawing_text_is_searchable(tmp_path):
    source = docx(tmp_path / "a.docx", "body", parts={"word/diagrams/data1.xml": (
        '<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:r><a:t>drawing phrase</a:t></a:r></a:p>'
    )})
    assert word_may_match(source, SearchOptions(tmp_path, "drawing phrase"))


@pytest.mark.parametrize("extra", [
    '<w:fldSimple w:instr="PAGE"/>', '<w:r><w:fldChar/></w:r>',
    '<w:r><w:sym/></w:r>', '<w:altChunk/>',
])
def test_generated_content_falls_back_to_pdf(tmp_path, extra):
    source = docx(tmp_path / "a.docx", "unrelated", extra)
    assert word_may_match(source, SearchOptions(tmp_path, "xyz"))


def test_regex_legacy_and_failed_extraction_are_candidates(tmp_path):
    source = docx(tmp_path / "a.docx", "unrelated")
    assert word_may_match(source, SearchOptions(tmp_path, "x.y", use_regex=True))
    legacy = tmp_path / "a.doc"
    legacy.write_bytes(b"legacy")
    assert word_may_match(legacy, SearchOptions(tmp_path, "xyz"))
    source.write_bytes(b"broken zip")
    assert word_may_match(source, SearchOptions(tmp_path, "xyz"))


def test_positive_stops_reading_and_cancellation_propagates(tmp_path, monkeypatch):
    source = docx(tmp_path / "a.docx", "needle", parts={"word/later.xml": "broken XML"})
    opened = []
    original_open = ZipFile.open

    def open_part(archive, name, *args, **kwargs):
        opened.append(name)
        return original_open(archive, name, *args, **kwargs)

    monkeypatch.setattr(ZipFile, "open", open_part)
    assert word_may_match(source, SearchOptions(tmp_path, "needle"))
    assert opened == ["word/document.xml"]
    cancelled = Event()
    cancelled.set()
    with pytest.raises(ConversionCancelled):
        word_may_match(source, SearchOptions(tmp_path, "needle"), cancelled)
