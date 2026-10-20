from threading import Event
from zipfile import ZipFile

import pymupdf as fitz

from rgpdf.models import SearchOptions
from rgpdf.search import search_folder


def _docx(path, text, extra=""):
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r>{extra}</w:p></w:body></w:document>'
        ))
    return path


def test_nine_illustrated_documents_only_convert_four_phrase_hits_in_regex_mode(tmp_path, monkeypatch):
    phrase = "循環緩衝區"
    extras = '<w:pPr><w:numPr/></w:pPr><w:r><w:drawing/><w:sym w:char="F0B7"/></w:r>'
    sources = [_docx(tmp_path / f"ch{i:02}.docx",
                     phrase if 5 <= i <= 8 else "循環與緩衝區是分開的字詞", extras)
               for i in range(1, 10)]
    pdf = tmp_path / "rendered.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), phrase, fontname="china-t")
        document.save(pdf)
    conversions = []

    def convert(path, **kwargs):
        conversions.append(path)
        return pdf

    monkeypatch.setattr("rgpdf.search.convert_word_to_pdf", convert)
    report = search_folder(SearchOptions(tmp_path, phrase, use_regex=True,
                                         search_scope="word", stem_glob="ch0*"))
    assert not report.warnings and report.scanned_files == 9
    assert conversions == sources[4:8]
    assert [result.path for result in report.documents] == sources[4:8]


def _pdf(path, text):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), text)
        document.save(path)
    return path


def test_only_candidates_convert_and_pdf_is_authoritative(tmp_path, monkeypatch):
    sources = [_docx(tmp_path / f"{i}.docx", text) for i, text in enumerate(
        ("abc xyz", "needle", "needle needle")
    )]
    pdfs = [_pdf(tmp_path / f"cache-{i}.pdf", text) for i, text in enumerate(
        ("no actual hit", "needle needle needle")
    )]
    calls, candidates, matches = [], [], []

    def convert(path, **kwargs):
        calls.append(path)
        return pdfs[sources.index(path) - 1]

    monkeypatch.setattr("rgpdf.search.convert_word_to_pdf", convert)
    report = search_folder(
        SearchOptions(tmp_path, "needle", search_scope="word"),
        candidate_found=lambda path, count: candidates.append((path, count)),
        match_found=lambda source, relative, pdf, match: matches.append(match),
    )
    assert calls == sources[1:]
    assert candidates == [(sources[1], 1), (sources[2], 2)]
    assert report.scanned_files == 3 and not report.warnings
    assert [document.path for document in report.documents] == [sources[2]]
    assert len(matches) == 3 and all(match.highlights for match in matches)


def test_screening_continues_and_ready_pdf_bypasses_blocked_conversion(tmp_path, monkeypatch):
    first = _docx(tmp_path / "a.docx", "needle")
    second = _docx(tmp_path / "b.docx", "needle")
    skipped = _docx(tmp_path / "c.docx", "abc xyz")
    direct = _pdf(tmp_path / "d.pdf", "needle")
    converted = _pdf(tmp_path / "converted.pdf", "needle")
    converting, screened_second, release = Event(), Event(), Event()
    calls, found = [], []
    from rgpdf.word_screening import word_may_match

    def screen(path, *args):
        if path == second:
            assert converting.wait(3)
            screened_second.set()
        return word_may_match(path, *args)

    def convert(path, **kwargs):
        calls.append(path)
        if path == first:
            converting.set()
            assert screened_second.wait(3), "initial screening must not wait for conversion"
            assert release.wait(3), "a ready PDF must be searched before this export finishes"
        return converted

    def complete(document):
        found.append(document.path)
        if document.path == direct:
            release.set()

    monkeypatch.setattr("rgpdf.search.word_may_match", screen)
    monkeypatch.setattr("rgpdf.search.convert_word_to_pdf", convert)
    try:
        report = search_folder(
            SearchOptions(tmp_path, "needle"), paths=[first, second, skipped, direct],
            document_found=complete,
        )
    finally:
        release.set()
    assert not report.warnings and report.scanned_files == 4
    assert found == [direct, first, second]
    assert calls == [first, second]


def test_cache_bypasses_word_screening_and_converter(tmp_path, monkeypatch):
    source = _docx(tmp_path / "a.docx", "unrelated")
    cached = _pdf(tmp_path / "cached.pdf", "needle")
    monkeypatch.setattr("rgpdf.search.cached_word_pdf", lambda path: cached)

    def forbidden(*args, **kwargs):
        raise AssertionError("cached PDF must bypass screening and export")

    monkeypatch.setattr("rgpdf.search.word_may_match", forbidden)
    monkeypatch.setattr("rgpdf.search.convert_word_to_pdf", forbidden)
    report = search_folder(SearchOptions(tmp_path, "needle", search_scope="word"))
    assert not report.warnings
    assert len(report.documents) == 1 and report.documents[0].preview_path == cached


def test_regex_and_unreadable_docx_go_directly_to_pdf(tmp_path, monkeypatch):
    valid = _docx(tmp_path / "valid.docx", "unrelated")
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"broken")
    pdf = _pdf(tmp_path / "cached.pdf", "needle")
    calls = []

    def convert(path, **kwargs):
        calls.append(path)
        return pdf

    monkeypatch.setattr("rgpdf.search.convert_word_to_pdf", convert)
    for regex, paths in ((False, [broken]), (True, [valid])):
        report = search_folder(SearchOptions(tmp_path, "n.edle" if regex else "needle", use_regex=regex), paths=paths)
        assert not report.warnings and len(report.documents) == 1
    assert calls == [broken, valid]
