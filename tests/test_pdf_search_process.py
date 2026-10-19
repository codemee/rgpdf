from contextlib import contextmanager
import os
from pathlib import Path
from threading import Event
import time

import pymupdf as fitz
import pytest

from rgpdf.models import DocumentMatch, SearchOptions, TextMatch
from rgpdf.pdf_search_process import PdfSearchProcess, PdfSearchProcessError
from rgpdf.preparation import BackgroundWordPreparation
from rgpdf.search import search_folder
from rgpdf.word_conversion import ConversionCancelled


def _pdf(path, text="needle needle"):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), text)
        document.save(path)


def test_process_streams_matches_reuses_child_and_recovers_after_bad_pdf(tmp_path):
    path = tmp_path / "good.pdf"
    _pdf(path)
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a PDF")
    matches = []
    process = PdfSearchProcess(SearchOptions(tmp_path, "needle"))
    with process:
        first = process.search(path, path, matches.append)
        pid = process._process.pid
        assert pid != os.getpid()
        assert tuple(matches) == first.matches
        assert len(matches) == 2 and matches[0].highlights
        with pytest.raises(PdfSearchProcessError):
            process.search(bad, bad)
        second = process.search(path, path)
        assert second == first
        assert process._process.pid == pid
    assert process._process is None


def test_isolated_search_keeps_incremental_source_and_preview_paths(tmp_path):
    source = tmp_path / "source.docx"
    source.touch()
    preview = tmp_path / "preview.pdf"
    _pdf(preview)
    found = []
    report = search_folder(
        SearchOptions(tmp_path, "needle", search_scope="word"),
        prepare_word=lambda path, cancel: preview,
        isolate_pdf_search=True,
        match_found=lambda path, relative, pdf, match: found.append((path, relative, pdf)),
    )
    assert not report.warnings
    assert found == [(source, Path("source.docx"), preview)] * 2
    assert report.documents[0].path == source
    assert report.documents[0].preview_path == preview


def _busy_server(connection, options):
    """Hold this interpreter's GIL while the parent keeps converting documents."""
    import sys

    try:
        while True:
            request = connection.recv()
            if request is None:
                return
            preview, source = request
            match = TextMatch("needle", "needle", 0, 6, 0, 0, ())
            connection.send(("match", match))
            previous = sys.getswitchinterval()
            sys.setswitchinterval(10)
            try:
                deadline = time.monotonic() + 0.5
                while time.monotonic() < deadline:
                    pass
            finally:
                sys.setswitchinterval(previous)
            connection.send(("result", DocumentMatch(
                source, source.relative_to(options.root), (match,), preview,
            )))
    finally:
        connection.close()


def test_background_conversion_finishes_while_search_child_holds_gil(tmp_path, monkeypatch):
    sources = [tmp_path / f"file-{index}.docx" for index in range(8)]
    for source in sources:
        source.touch()
    preview = tmp_path / "preview.pdf"
    preview.write_bytes(b"mock PDF search")
    first_conversion, start_search, all_converted = Event(), Event(), Event()
    converted = []

    @contextmanager
    def session():
        yield []

    def convert(path, **kwargs):
        if path == sources[0]:
            first_conversion.set()
        else:
            assert start_search.wait(5)
        converted.append(path)
        if len(converted) == len(sources):
            all_converted.set()
        return preview

    monkeypatch.setattr("rgpdf.preparation.word_conversion_session", session)
    monkeypatch.setattr("rgpdf.preparation.convert_word_to_pdf", convert)
    monkeypatch.setattr("rgpdf.pdf_search_process._serve", _busy_server)
    preparation = BackgroundWordPreparation()
    options = SearchOptions(tmp_path, "needle", search_scope="word")
    try:
        preparation.update(options)
        assert first_conversion.wait(3)
        with PdfSearchProcess(options) as process:
            def searching(match):
                start_search.set()
                assert all_converted.wait(3)
                assert process._process.is_alive()

            result = process.search(preparation.get_pdf(sources[0]), sources[0], searching)
        assert result.matches
        assert converted == sources
    finally:
        start_search.set()
        preparation.close(wait=True)


def test_process_cancellation_stops_busy_child(tmp_path, monkeypatch):
    monkeypatch.setattr("rgpdf.pdf_search_process._serve", _busy_server)
    cancelled = Event()
    process = PdfSearchProcess(SearchOptions(tmp_path, "needle"), cancelled)
    with process:
        with pytest.raises(ConversionCancelled):
            process.search(tmp_path / "preview.pdf", tmp_path / "source.docx", lambda match: cancelled.set())
        assert process._process is None
