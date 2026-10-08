from __future__ import annotations

import sys
import os
from types import ModuleType, SimpleNamespace
from pathlib import Path

from rgpdf.word_conversion import (
    _word_to_pdf,
    cleanup_word_cache,
    clear_word_cache,
    convert_word_to_pdf,
)


def test_conversion_falls_back_and_reuses_cache(tmp_path: Path) -> None:
    source = tmp_path / "sample.docx"
    source.write_bytes(b"word document")
    cache = tmp_path / "cache"
    calls: list[str] = []

    def fail(_source: Path, _destination: Path, _cancel_event) -> None:
        calls.append("word")
        raise RuntimeError("Word is unavailable")

    def succeed(_source: Path, destination: Path, _cancel_event) -> None:
        calls.append("libreoffice")
        destination.write_bytes(b"%PDF-test")

    converters = [("word", fail), ("libreoffice", succeed)]
    first = convert_word_to_pdf(source, cache_root=cache, converters=converters)
    second = convert_word_to_pdf(source, cache_root=cache, converters=converters)

    assert first == second
    assert first.read_bytes() == b"%PDF-test"
    assert calls == ["word", "libreoffice"]


def test_word_conversion_disables_link_updates_without_invalid_open_argument(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "sample.docx"
    destination = tmp_path / "sample.pdf"
    source.touch()
    open_arguments = {}

    class FakeDocument:
        def ExportAsFixedFormat(self, **arguments) -> None:
            Path(arguments["OutputFileName"]).write_bytes(b"%PDF-test")

        def Close(self, **_arguments) -> None:
            pass

    class FakeDocuments:
        def Open(self, **arguments):
            open_arguments.update(arguments)
            return FakeDocument()

    application = SimpleNamespace(
        Visible=True,
        DisplayAlerts=1,
        AutomationSecurity=0,
        Options=SimpleNamespace(UpdateLinksAtOpen=True),
        Documents=FakeDocuments(),
        Quit=lambda **_arguments: None,
    )
    pythoncom = ModuleType("pythoncom")
    pythoncom.CoInitialize = lambda: None
    pythoncom.CoUninitialize = lambda: None
    client = ModuleType("win32com.client")
    client.DispatchEx = lambda _name: application
    win32com = ModuleType("win32com")
    win32com.client = client
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", win32com)
    monkeypatch.setitem(sys.modules, "win32com.client", client)

    _word_to_pdf(source, destination, None)

    assert destination.is_file()
    assert application.Options.UpdateLinksAtOpen is False
    assert "UpdateLinks" not in open_arguments
    assert open_arguments["ReadOnly"] is True


def test_cleanup_removes_expired_then_oldest_entries_to_size_limit(tmp_path: Path) -> None:
    now = 2_000_000_000.0
    old = tmp_path / "old.pdf"
    least_recent = tmp_path / "least-recent.pdf"
    newest = tmp_path / "newest.pdf"
    old.write_bytes(b"1234")
    least_recent.write_bytes(b"123456")
    newest.write_bytes(b"123456")
    os.utime(old, (now - 31 * 24 * 60 * 60, now - 31 * 24 * 60 * 60))
    os.utime(least_recent, (now - 20, now - 20))
    os.utime(newest, (now - 10, now - 10))

    result = cleanup_word_cache(
        cache_root=tmp_path, max_age_days=30, max_bytes=10, now=now
    )

    assert not old.exists()
    assert not least_recent.exists()
    assert newest.exists()
    assert result.removed_files == 2
    assert result.removed_bytes == 10
    assert result.failed_files == 0


def test_clear_word_cache_removes_all_pdf_entries_only(tmp_path: Path) -> None:
    (tmp_path / "one.pdf").write_bytes(b"one")
    (tmp_path / "two.tmp.pdf").write_bytes(b"two")
    keep = tmp_path / "keep.txt"
    keep.write_text("keep", encoding="utf-8")

    result = clear_word_cache(cache_root=tmp_path)

    assert result.removed_files == 2
    assert result.removed_bytes == 6
    assert keep.exists()
