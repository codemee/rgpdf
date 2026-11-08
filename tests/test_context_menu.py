import ctypes
import json
from pathlib import Path
import plistlib
import shlex
import subprocess
import sys
from uuid import uuid4

import pytest
from PySide6.QtCore import QSettings

from rgpdf import context_menu
from rgpdf.app import main, open_startup_paths, parse_arguments
from rgpdf.main_window import MainWindow


def test_startup_paths_accept_folders_files_and_option_like_names(tmp_path):
    folder = tmp_path / 'folder with spaces'
    folder.mkdir()
    file = folder / 'document.pdf'
    file.touch()
    options = parse_arguments(['--', str(folder), str(file), '-folder'])
    assert options.paths == [str(folder), str(file), '-folder']
    opened = []
    class Window:
        def open_folder(self, path):
            opened.append(path)
    open_startup_paths(Window(), options.paths[:2])
    assert opened == [folder, folder]
    with pytest.raises(SystemExit):
        parse_arguments(['--install-context-menu', '--remove-context-menu'])


def test_registration_cli_does_not_start_gui(monkeypatch):
    calls = []
    monkeypatch.setattr(context_menu, 'set_enabled', lambda value: calls.append(value))
    assert main(['--install-context-menu']) == 0
    assert main(['--remove-context-menu']) == 0
    assert calls == [True, False]
    def failed(_):
        raise PermissionError('test failure')
    monkeypatch.setattr(context_menu, 'set_enabled', failed)
    assert main(['--install-context-menu']) == 1


@pytest.mark.skipif(sys.platform not in {'win32', 'darwin'}, reason='Supported file manager platform')
def test_registration_button_updates_all_tabs_without_touching_os(qtbot, tmp_path, monkeypatch):
    state = []
    monkeypatch.setattr(context_menu, 'is_installed', lambda: bool(state))
    def enabled(value, **_):
        state[:] = [True] if value else []
    monkeypatch.setattr(context_menu, 'set_enabled', enabled)
    monkeypatch.setattr('rgpdf.main_window.QMessageBox.information', lambda *args: None)
    settings = QSettings(str(tmp_path / 'context.ini'), QSettings.Format.IniFormat)
    settings.setValue('appearance/language', 'en')
    window = MainWindow(lambda _: None, settings)
    qtbot.addWidget(window)
    window.show()
    first = window.current_tab
    other = tmp_path / 'other'
    other.mkdir()
    second = window.open_folder(other)
    assert first.context_menu_button.isCheckable()
    assert not second.context_menu_button.isChecked()
    assert second.context_menu_button.toolTip().startswith('Add ')
    second.context_menu_button.click()
    assert state and first.context_menu_button.isChecked() and second.context_menu_button.isChecked()
    assert second.context_menu_button.toolTip().startswith('Remove ')
    second.context_menu_button.click()
    assert not state and not first.context_menu_button.isChecked() and not second.context_menu_button.isChecked()
    assert second.context_menu_button.toolTip().startswith('Add ')
    def failed(*args, **kwargs):
        raise PermissionError('test failure')
    monkeypatch.setattr(context_menu, 'set_enabled', failed)
    monkeypatch.setattr('rgpdf.main_window.QMessageBox.warning', lambda *args: None)
    second.context_menu_button.click()
    assert not second.context_menu_button.isChecked()
    window.close()
    qtbot.waitUntil(lambda: not window.isVisible())


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Windows registry and argv parser')
def test_windows_per_user_registration_and_quoted_roots(tmp_path, monkeypatch):
    import winreg
    root = rf'Software\rgpdf-test-{uuid4()}'
    keys = ((root + r'\Folder', '%1'), (root + r'\Background', '%V'))
    file_keys = tuple((root + '\\File' + extension, '%1') for extension in ('.pdf', '.doc', '.docx'))
    monkeypatch.setattr(context_menu, 'WINDOWS_KEYS', keys)
    monkeypatch.setattr(context_menu, 'WINDOWS_FILE_KEYS', file_keys)
    monkeypatch.setattr(context_menu, 'launch_command', lambda: [r'C:\App space\rgpdf.exe'])
    try:
        assert not context_menu.is_installed()
        context_menu.set_enabled(True, title='Open test rgPDF')
        context_menu.set_enabled(True, title='Open test rgPDF')
        assert context_menu.is_installed()
        for key, _ in keys:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                assert winreg.QueryValueEx(handle, '')[0] == 'Open test rgPDF'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, keys[0][0]) as handle:
            assert winreg.QueryValueEx(handle, 'MultiSelectModel')[0] == 'Document'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, keys[1][0]) as handle:
            with pytest.raises(FileNotFoundError):
                winreg.QueryValueEx(handle, 'MultiSelectModel')
        # Repair previously registered commands whose Single model hides the
        # background verb even though their executable paths are up to date.
        for key, _ in keys:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as handle:
                winreg.SetValueEx(handle, 'MultiSelectModel', 0, winreg.REG_SZ, 'Single')
        assert not context_menu.is_installed()
        context_menu.set_enabled(True)
        assert context_menu.is_installed()
        for key, placeholder in file_keys:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key + r'\command') as handle:
                assert winreg.QueryValueEx(handle, '')[0] == context_menu.windows_command(placeholder, is_file=True)
        api = ctypes.WinDLL('shell32')
        api.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        api.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
        kernel = ctypes.WinDLL('kernel32')
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        for folder in ('C:\\', '\\\\server\\share\\', r'C:\space folder\中文'):
            count = ctypes.c_int()
            argv = api.CommandLineToArgvW(context_menu.windows_command('%1').replace('%1', folder),
                                          ctypes.byref(count))
            try:
                assert [argv[i] for i in range(count.value)] == [r'C:\App space\rgpdf.exe', '--', folder + r'\.']
            finally:
                kernel.LocalFree(argv)
        for file in (r'C:\space folder\中文.pdf', r'C:\space folder\notes.doc', r'C:\space folder\notes.docx'):
            count = ctypes.c_int()
            argv = api.CommandLineToArgvW(context_menu.windows_command('%1', is_file=True).replace('%1', file),
                                          ctypes.byref(count))
            try:
                assert [argv[i] for i in range(count.value)] == [r'C:\App space\rgpdf.exe', '--', file]
            finally:
                kernel.LocalFree(argv)
        context_menu.set_enabled(False)
        context_menu.set_enabled(False)
        assert not context_menu.is_installed()
        for key, _ in keys + file_keys:
            with pytest.raises(FileNotFoundError):
                winreg.OpenKey(winreg.HKEY_CURRENT_USER, key)
    finally:
        for key, _ in keys + file_keys:
            for owned in (key + r'\command', key):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, owned)
                except FileNotFoundError:
                    pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, root)
        except FileNotFoundError:
            pass


def test_finder_workflow_install_remove_and_safe_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(context_menu.sys, 'platform', 'darwin')
    root = tmp_path / 'Services' / 'Open in rgPDF.workflow'
    monkeypatch.setattr(context_menu, 'service_path', lambda: root)
    monkeypatch.setattr(context_menu, 'launch_command', lambda: ['/App space/rgpdf', '-m', 'rgpdf'])
    refresh = []
    monkeypatch.setattr(context_menu.subprocess, 'run', lambda *args, **kwargs: refresh.append(args))
    assert not context_menu.is_installed()
    context_menu.set_enabled(True)
    context_menu.set_enabled(True)
    assert context_menu.is_installed()
    info = plistlib.loads((root / 'Contents' / 'Info.plist').read_bytes())
    assert set(info['NSServices'][0]['NSSendFileTypes']) == set(context_menu.SERVICE_TYPES)
    info['NSServices'][0]['NSSendFileTypes'] = ['public.folder']
    (root / 'Contents' / 'Info.plist').write_bytes(plistlib.dumps(info))
    assert not context_menu.is_installed()
    context_menu.set_enabled(True)
    workflow = plistlib.loads((root / 'Contents' / 'document.wflow').read_bytes())
    action = workflow['actions'][0]['action']['ActionParameters']
    assert action['inputMethod'] == 1
    assert "'/App space/rgpdf' -m rgpdf -- \"$@\"" in action['COMMAND_STRING']
    context_menu.set_enabled(False)
    context_menu.set_enabled(False)
    assert not root.exists()
    assert len(refresh) == 5
    root.mkdir()
    marker = root / 'unrelated.txt'
    marker.write_text('keep')
    with pytest.raises(FileExistsError):
        context_menu.set_enabled(True)
    with pytest.raises(FileExistsError):
        context_menu.set_enabled(False)
    assert marker.read_text() == 'keep'


def test_frozen_finder_command_uses_bundle_and_new_instance(monkeypatch):
    monkeypatch.setattr(context_menu.sys, 'platform', 'darwin')
    monkeypatch.setattr(context_menu.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(context_menu.sys, 'executable', '/Applications/App space/rgpdf.app/Contents/MacOS/rgpdf')
    _, workflow = context_menu.finder_workflow()
    script = workflow['actions'][0]['action']['ActionParameters']['COMMAND_STRING']
    bundle = Path(sys.executable).absolute().parents[2]
    assert f'/usr/bin/open -n -a {shlex.quote(str(bundle))} --args -- "$@"' in script


@pytest.mark.skipif(sys.platform != 'darwin', reason='Native macOS Automator execution')
@pytest.mark.parametrize('as_file', [False, True])
def test_finder_workflow_runs_with_folder_arguments(tmp_path, monkeypatch, qtbot, as_file):
    output = tmp_path / 'arguments.json'
    script = f'import json,sys; from pathlib import Path; Path({str(output)!r}).write_text(json.dumps(sys.argv[1:]))'
    monkeypatch.setattr(context_menu, 'launch_command', lambda: [sys.executable, '-c', script])
    info, workflow = context_menu.finder_workflow()
    contents = tmp_path / 'Open.workflow' / 'Contents'
    contents.mkdir(parents=True)
    (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
    document = contents / 'document.wflow'
    document.write_bytes(plistlib.dumps(workflow))
    folder = tmp_path / 'folder with spaces & quotes'
    folder.mkdir()
    target = folder
    if as_file:
        target = folder / '中文 document.pdf'
        target.touch()
    result = subprocess.run(['/usr/bin/automator', '-i', str(target), str(document)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    qtbot.waitUntil(output.is_file, timeout=5000)
    assert json.loads(output.read_text()) == ['--', str(target)]
