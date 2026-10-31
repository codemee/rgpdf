from threading import Event

import pytest

from rgpdf import word_conversion
from rgpdf.conversion_service import WordConversionService


@pytest.fixture
def renderer(qtbot, tmp_path, monkeypatch):
    started, release = Event(), Event()
    calls = []

    def convert(source, target, cancel):
        calls.append(source.name)
        if source.stem == 'first':
            started.set()
            assert release.wait(10)
        if source.stem == 'bad':
            raise OSError('Conversion failed')
        target.write_bytes(b'%PDF-' + source.name.encode())

    monkeypatch.setattr(word_conversion, '_cache_root', lambda: tmp_path / 'cache')
    monkeypatch.setattr(word_conversion, 'available_converters', lambda: [('libreoffice', convert)])
    service = WordConversionService()
    try:
        yield service, calls, started, release
    finally:
        release.set()
        service.close()
        qtbot.waitUntil(service.is_stopped, timeout=10000)


def _source(root, stem):
    path = root / f'{stem}.docx'
    path.write_bytes(b'source')
    return path


def test_fifo_dedup_and_independent_subscriber_cancel(qtbot, tmp_path, renderer):
    service, calls, started, release = renderer
    a = service.submit(_source(tmp_path, 'first'))
    qtbot.waitUntil(started.is_set)
    b = service.submit(_source(tmp_path, 'second'))
    shared = service.submit(tmp_path / 'first.docx')
    unused = service.submit(_source(tmp_path, 'unused'))
    c = service.submit(_source(tmp_path, 'third'))
    a.release()
    unused.release()
    assert calls == ['first.docx']
    assert service.state(tmp_path / 'second.docx') == ('queued', 1)
    release.set()
    qtbot.waitUntil(lambda: c.future.done())
    assert shared.future.result().is_file()
    assert b.future.result().is_file()
    assert calls == ['first.docx', 'second.docx', 'third.docx']
    b.release()
    shared.release()
    c.release()


def test_cache_bypasses_busy_renderer_and_failure_does_not_stop_queue(qtbot, tmp_path, renderer):
    service, calls, started, release = renderer
    cached = _source(tmp_path, 'cached')
    cache = word_conversion._cache_root()
    cache.mkdir()
    pdf = word_conversion._cache_path(cached, 'microsoft-word', cache)
    pdf.write_bytes(b'%PDF-cached')
    first = service.submit(_source(tmp_path, 'first'))
    qtbot.waitUntil(started.is_set)
    ready = service.submit(cached)
    assert ready.future.done() and ready.future.result() == pdf
    bad = service.submit(_source(tmp_path, 'bad'))
    good = service.submit(_source(tmp_path, 'good'))
    release.set()
    qtbot.waitUntil(lambda: good.future.done())
    assert bad.future.exception() is not None
    assert good.future.result().is_file()
    assert 'cached.docx' not in calls
    for ticket in (first, ready, bad, good):
        ticket.release()


def test_changed_queued_source_is_not_published_as_old_result(qtbot, tmp_path, renderer):
    service, calls, started, release = renderer
    first = service.submit(_source(tmp_path, 'first'))
    qtbot.waitUntil(started.is_set)
    source = _source(tmp_path, 'changing')
    changing = service.submit(source)
    source.write_bytes(b'changed contents')
    release.set()
    qtbot.waitUntil(lambda: changing.future.done())
    assert 'Source changed' in str(changing.future.exception())
    first.release()
    changing.release()
