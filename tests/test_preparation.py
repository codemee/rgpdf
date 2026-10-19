from contextlib import contextmanager
import os
from threading import Event, Thread, get_ident

import pytest

from rgpdf.models import SearchOptions
from rgpdf.preparation import BackgroundWordPreparation
from rgpdf.word_conversion import CacheCleanupResult, ConversionCancelled


@pytest.fixture
def converter(monkeypatch, tmp_path):
    calls = []
    session_threads = []

    @contextmanager
    def session():
        session_threads.append(("open", get_ident()))
        try:
            yield []
        finally:
            session_threads.append(("close", get_ident()))

    def convert(path, **kwargs):
        calls.append(path)
        kwargs["conversion_started"]()
        output = tmp_path / f"cached-{len(calls)}.pdf"
        output.write_bytes(b"pdf")
        return output

    monkeypatch.setattr("rgpdf.preparation.word_conversion_session", session)
    monkeypatch.setattr("rgpdf.preparation.convert_word_to_pdf", convert)
    return calls, session_threads, convert


def test_folder_selection_prepares_without_search_and_search_reuses_it(tmp_path, converter):
    calls, threads, _ = converter
    source = tmp_path / "ch01.docx"
    source.touch()
    idle = Event()
    stages = []
    preparation = BackgroundWordPreparation(
        converting=stages.append, busy_changed=lambda busy: idle.set() if not busy else None,
    )
    try:
        preparation.update(SearchOptions(tmp_path, "", search_scope="word"))
        assert idle.wait(3)
        assert calls == [source]
        assert preparation.get_pdf(source).is_file()
        assert calls == [source]
        assert stages == ["ch01.docx", ""]
    finally:
        preparation.close(wait=True)
    assert threads[0] == ("open", threads[-1][1])
    assert threads[-1][0] == "close"
    assert threads[0][1] != get_ident()


def test_changed_filter_removes_pending_files_and_adds_new_ones(tmp_path, converter, monkeypatch):
    calls, _, convert = converter
    sources = [tmp_path / name for name in ("ch01.docx", "ch02.docx", "ch10.docx")]
    for source in sources:
        source.touch()
    started, release, idle = Event(), Event(), Event()

    def blocked(path, **kwargs):
        if path == sources[0]:
            started.set()
            assert release.wait(3)
        return convert(path, **kwargs)

    monkeypatch.setattr("rgpdf.preparation.convert_word_to_pdf", blocked)
    preparation = BackgroundWordPreparation(busy_changed=lambda busy: idle.set() if not busy else None)
    try:
        preparation.update(SearchOptions(tmp_path, "", search_scope="word", stem_glob="ch0*"))
        assert started.wait(3)
        preparation.update(SearchOptions(tmp_path, "", search_scope="word", stem_glob="ch1*"))
        release.set()
        assert idle.wait(3)
        assert calls == [sources[0], sources[2]]
    finally:
        release.set()
        preparation.close(wait=True)


def test_latest_scope_and_recursion_replace_queued_work(tmp_path, converter, monkeypatch):
    calls, _, convert = converter
    first = tmp_path / "first.docx"
    first.touch()
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "later.docx").touch()
    started, release, idle = Event(), Event(), Event()

    def blocked(path, **kwargs):
        started.set()
        assert release.wait(3)
        return convert(path, **kwargs)

    monkeypatch.setattr("rgpdf.preparation.convert_word_to_pdf", blocked)
    preparation = BackgroundWordPreparation(busy_changed=lambda busy: idle.set() if not busy else None)
    try:
        preparation.update(SearchOptions(tmp_path, "", search_scope="word"))
        assert started.wait(3)
        preparation.update(SearchOptions(tmp_path, "", search_scope="word", recursive=False))
        preparation.update(SearchOptions(tmp_path, "", search_scope="pdf"))
        release.set()
        assert idle.wait(3)
        assert calls == [first]
    finally:
        release.set()
        preparation.close(wait=True)


def test_get_pdf_refreshes_changed_source_and_missing_cache(tmp_path, converter):
    calls, _, _ = converter
    source = tmp_path / "source.docx"
    source.write_bytes(b"one")
    preparation = BackgroundWordPreparation()
    try:
        first = preparation.get_pdf(source)
        os.utime(first, (1, 1))
        assert preparation.get_pdf(source) == first
        assert first.stat().st_atime > 1
        assert first.stat().st_mtime == 1
        source.write_bytes(b"changed source")
        second = preparation.get_pdf(source)
        assert second != first
        second.unlink()
        assert preparation.get_pdf(source).is_file()
        assert calls == [source, source, source]
    finally:
        preparation.close(wait=True)


def test_cancelling_search_wait_does_not_cancel_background_preparation(tmp_path, converter, monkeypatch):
    _, _, convert = converter
    source = tmp_path / "source.docx"
    source.touch()
    started, release, cancelled = Event(), Event(), Event()

    def blocked(path, **kwargs):
        started.set()
        assert release.wait(3)
        return convert(path, **kwargs)

    monkeypatch.setattr("rgpdf.preparation.convert_word_to_pdf", blocked)
    preparation = BackgroundWordPreparation()
    try:
        preparation.update(SearchOptions(tmp_path, "", search_scope="word"))
        assert started.wait(3)
        cancelled.set()
        with pytest.raises(ConversionCancelled):
            preparation.get_pdf(source, cancelled)
        release.set()
        assert preparation.get_pdf(source).is_file()
    finally:
        release.set()
        preparation.close(wait=True)


def test_search_waits_for_inflight_background_result_without_duplicate_conversion(
    tmp_path, converter, monkeypatch
):
    import pymupdf as fitz
    from rgpdf.search import search_folder

    calls, _, convert = converter
    source = tmp_path / "source.docx"
    source.touch()
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "needle")
        pdf_bytes = document.tobytes()
    started, requested, release = Event(), Event(), Event()

    def blocked(path, **kwargs):
        started.set()
        assert release.wait(3)
        pdf = convert(path, **kwargs)
        pdf.write_bytes(pdf_bytes)
        return pdf

    monkeypatch.setattr("rgpdf.preparation.convert_word_to_pdf", blocked)
    preparation = BackgroundWordPreparation()
    results, failures = [], []

    def prepare(path, cancel):
        requested.set()
        return preparation.get_pdf(path, cancel)

    def search():
        try:
            results.append(search_folder(
                SearchOptions(tmp_path, "needle", search_scope="word"), prepare_word=prepare,
            ))
        except Exception as exc:
            failures.append(exc)

    thread = Thread(target=search)
    try:
        preparation.update(SearchOptions(tmp_path, "", search_scope="word"))
        assert started.wait(3)
        thread.start()
        assert requested.wait(3)
        release.set()
        thread.join(3)
        assert not thread.is_alive() and not failures
        assert len(results) == 1 and not results[0].warnings
        assert results[0].documents[0].path == source
        assert calls == [source]
    finally:
        release.set()
        preparation.close(wait=True)
        if thread.ident is not None:
            thread.join(3)


def test_clearing_cache_invalidates_prepared_results(tmp_path, converter, monkeypatch):
    calls, _, _ = converter
    source = tmp_path / "source.docx"
    source.touch()
    idle = Event()
    cleared = []

    def clear():
        cleared.append(True)
        return CacheCleanupResult(removed_files=1)

    monkeypatch.setattr("rgpdf.preparation.clear_word_cache", clear)
    preparation = BackgroundWordPreparation(busy_changed=lambda busy: idle.set() if not busy else None)
    try:
        preparation.update(SearchOptions(tmp_path, "", search_scope="word"))
        assert idle.wait(3)
        assert preparation.clear_cache().removed_files == 1
        assert cleared == [True]
        assert preparation.get_pdf(source).is_file()
        assert calls == [source, source]
    finally:
        preparation.close(wait=True)


def test_closing_preparation_cancels_active_conversion_and_cleans_up(tmp_path, converter, monkeypatch):
    _, threads, _ = converter
    source = tmp_path / "source.docx"
    source.touch()
    started = Event()

    def blocked(path, **kwargs):
        started.set()
        assert kwargs["cancel_event"].wait(3)
        raise ConversionCancelled()

    monkeypatch.setattr("rgpdf.preparation.convert_word_to_pdf", blocked)
    preparation = BackgroundWordPreparation()
    try:
        preparation.update(SearchOptions(tmp_path, "", search_scope="word"))
        assert started.wait(3)
    finally:
        preparation.close(wait=True)
    assert [phase for phase, thread in threads] == ["open", "close"]
    assert len({thread for phase, thread in threads}) == 1
