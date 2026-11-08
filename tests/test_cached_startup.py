import hashlib
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

from rgpdf import context_menu, startup


def test_cached_runtime_registers_outer_launcher(monkeypatch, tmp_path):
    outer = tmp_path / 'App with spaces' / 'rgpdf.exe'
    outer.parent.mkdir()
    outer.touch()
    monkeypatch.setattr(startup.sys, 'platform', 'win32')
    monkeypatch.setattr(startup.sys, 'frozen', True, raising=False)
    monkeypatch.setenv('RGPDF_LAUNCHER_PATH', str(outer))
    assert context_menu.launch_command() == [str(outer)]
    monkeypatch.setenv('RGPDF_LAUNCHER_PATH', 'relative.exe')
    assert startup.launcher_path() is None


def test_startup_marker_is_confined_and_not_inherited(monkeypatch, tmp_path):
    outer = tmp_path / 'rgpdf.exe'
    outer.touch()
    monkeypatch.setattr(startup.sys, 'platform', 'win32')
    monkeypatch.setattr(startup.sys, 'frozen', True, raising=False)
    monkeypatch.setenv('RGPDF_LAUNCHER_PATH', str(outer))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    folder = tmp_path / 'rgpdf' / 'logs' / 'cached-launcher'
    folder.mkdir(parents=True)
    marker = folder / 'run.ready'
    monkeypatch.setenv('RGPDF_STARTUP_MARKER', str(marker))
    startup.mark_window_ready()
    assert marker.read_text().isdigit()
    assert 'RGPDF_STARTUP_MARKER' not in startup.os.environ
    other = tmp_path / 'outside.ready'
    monkeypatch.setenv('RGPDF_STARTUP_MARKER', str(other))
    startup.mark_window_ready()
    assert not other.exists()


def test_runtime_package_manifest_tracks_exact_files(tmp_path):
    source = tmp_path / 'runtime'
    source.mkdir()
    (source / 'rgpdf-runtime.exe').write_bytes(b'test fixture, not a PE executable')
    (source / '_internal').mkdir()
    (source / '_internal' / 'module.txt').write_text('content', encoding='utf-8')
    spec = importlib.util.spec_from_file_location('package_cached_runtime', Path(__file__).parents[1] / 'scripts/package_cached_runtime.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / 'packed'
    build = module.package_runtime(source, output)
    assert build == hashlib.sha256((output / 'runtime.zip').read_bytes()).hexdigest()
    manifest = json.loads((output / 'runtime.json').read_text())
    assert manifest['build_id'] == build
    with ZipFile(output / 'runtime.zip') as archive:
        assert set(archive.namelist()) == {'rgpdf-runtime.exe', '_internal/module.txt'}
        for entry in manifest['files']:
            data = archive.read(entry['path'])
            assert len(data) == entry['size']
            assert hashlib.sha256(data).hexdigest() == entry['sha256']
