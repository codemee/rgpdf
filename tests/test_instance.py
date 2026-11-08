import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PySide6.QtCore import QSettings

from rgpdf.app import deliver_external_request
from rgpdf.instance import AlreadyRunning, InstanceError, LocalInstance
from rgpdf.main_window import MainWindow


def test_new_window_bypasses_primary_instance(monkeypatch):
    from rgpdf.bootstrap import main
    calls = []
    monkeypatch.setattr('rgpdf.app.run_application', lambda args: calls.append(args.paths) or 7)

    def forbidden():
        pytest.fail('Independent windows must not contact or own the primary endpoint')

    assert main(['--new-window', 'folder'], _instance_factory=forbidden) == 7
    assert calls == [['folder']]


def test_runtime_hook_defers_qt_until_gui_owner(monkeypatch):
    import runpy
    from rgpdf.bootstrap import _prepare_gui
    calls = []
    qt = SimpleNamespace(create_embedded_qt_conf=lambda *args: calls.append(args))
    monkeypatch.setitem(sys.modules, '_pyi_rth_utils', SimpleNamespace(qt=qt))
    monkeypatch.setattr(sys, '_rgpdf_deferred_qt', None, raising=False)
    runpy.run_path(str(Path(__file__).parents[1] / 'scripts' / 'pyi_rth_defer_qt.py'))
    qt.create_embedded_qt_conf('PySide6', '/plugins')
    assert calls == []
    _prepare_gui()
    _prepare_gui()  # Registration is applied once.
    assert calls == [('PySide6', '/plugins')]
    sys._rgpdf_deferred_qt = None  # Restore the attribute for monkeypatch teardown.


@pytest.fixture
def endpoint():
    name = 'rgpdf-test-' + uuid4().hex[:16]
    address = rf'\\.\pipe\{name}' if sys.platform == 'win32' else os.path.join(tempfile.gettempdir(), name + '.sock')
    yield address
    if sys.platform != 'win32':
        Path(address + '.lock').unlink(missing_ok=True)


def test_forward_while_gui_is_still_starting_and_preserve_paths(endpoint):
    primary = LocalInstance(endpoint)
    secondary = LocalInstance(endpoint)
    try:
        assert not secondary.forward([])
        primary.start()  # No Qt event loop or GUI has been started.
        paths = [r'C:\folder with spaces\中文.pdf', '/another/folder']
        assert secondary.forward(paths)
        assert secondary.forward([])  # A no-argument launch activates the app.
        assert list(primary.pending()) == [paths, []]
        primary.stop_accepting()
        with pytest.raises(InstanceError):
            secondary.forward(paths)
    finally:
        secondary.close()
        primary.close()


def test_only_one_owner_and_endpoint_reusable_after_close(endpoint):
    first, other = LocalInstance(endpoint), LocalInstance(endpoint)
    try:
        first.start()
        with pytest.raises(AlreadyRunning):
            other.start()
    finally:
        other.close()
        first.close()
    replacement = LocalInstance(endpoint)
    try:
        replacement.start()
        assert LocalInstance(endpoint).forward(['replacement'])
        assert list(replacement.pending()) == [['replacement']]
    finally:
        replacement.close()


def test_secondary_exits_without_importing_gui_or_pdf(endpoint):
    primary = LocalInstance(endpoint)
    primary.start()
    try:
        code = f'''
import sys
from rgpdf.bootstrap import main
from rgpdf.instance import LocalInstance
result = main(['--', 'folder with spaces'], _instance_factory=lambda: LocalInstance({endpoint!r}))
print(result, any(name.startswith(('PySide6', 'pymupdf', 'rgpdf.app', 'rgpdf.search')) for name in sys.modules))
'''
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == '0 False'
        assert list(primary.pending()) == [[os.path.abspath('folder with spaces')]]
    finally:
        primary.close()


def test_bad_message_does_not_kill_server(endpoint):
    from rgpdf.instance import _connect, _receive, _send
    primary = LocalInstance(endpoint)
    primary.start()
    try:
        with _connect(endpoint) as connection:
            _receive(connection)
            _send(connection, {'protocol': 'wrong', 'paths': ['folder']})
            assert _receive(connection)['accepted'] is False
        assert LocalInstance(endpoint).forward(['valid'])
        assert list(primary.pending()) == [['valid']]
    finally:
        primary.close()


def test_external_request_reuses_tab_restores_window_and_file_parent(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / 'ipc.ini'), QSettings.Format.IniFormat)
    folder = tmp_path / 'folder with spaces'
    folder.mkdir()
    source = folder / 'document.pdf'
    source.touch()
    window = MainWindow(lambda _: None, settings)
    qtbot.addWidget(window)
    window.show()
    window.showMinimized()
    deliver_external_request(window, [str(source)])
    assert not window.isMinimized()
    assert window.tabs.count() == 1
    assert window.folder_edit.text() == str(folder.resolve())
    deliver_external_request(window, [str(folder)])
    assert window.tabs.count() == 1
    assert window.worker is None
    window.close()
    qtbot.waitUntil(lambda: not window.isVisible())
