import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tarfile

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checks = load('check')
sources = load('package_third_party_sources')
releases = load('release')
smoke = load('test_macos_startup')


def project(root, version='1.0.0'):
    (root / 'src/rgpdf').mkdir(parents=True, exist_ok=True)
    (root / 'tests').mkdir(exist_ok=True)
    (root / 'pyproject.toml').write_text(f'[project]\nname="rgpdf"\nversion="{version}"\n', encoding='utf-8')
    (root / 'src/rgpdf/__init__.py').write_text(f'__version__ = "{version}"\n', encoding='utf-8')
    (root / 'uv.lock').write_text(f'[[package]]\nname="rgpdf"\nversion="{version}"\n', encoding='utf-8')


def test_fingerprint_reuses_metadata_only_changes_but_tracks_code_and_environment(tmp_path):
    project(tmp_path)
    before = checks.fingerprint(tmp_path, {'python': 'a'})
    project(tmp_path, '1.0.1')
    (tmp_path / 'README.md').write_text('updated docs', encoding='utf-8')
    checks.validate_versions(tmp_path)
    assert checks.fingerprint(tmp_path, {'python': 'a'}) == before
    assert checks.fingerprint(tmp_path, {'python': 'b'}) != before
    code = tmp_path / 'src/rgpdf/worker.py'
    code.write_text('changed = True', encoding='utf-8')
    assert checks.fingerprint(tmp_path, {'python': 'a'}) != before
    code.unlink()
    (tmp_path / 'tests/test_new.py').write_text('def test_new(): pass', encoding='utf-8')
    assert checks.fingerprint(tmp_path, {'python': 'a'}) != before


def test_full_test_cache_reuse_targeted_failures_and_force(tmp_path, monkeypatch):
    project(tmp_path)
    monkeypatch.setattr(checks, 'environment', lambda: {})
    monkeypatch.delenv('PYTEST_ADDOPTS', raising=False)
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)
    assert checks.check(tmp_path, ['tests/test_one.py'], runner=run) == 0
    assert checks.check(tmp_path, [], runner=run) == 0
    assert len(calls) == 2  # A targeted pass did not certify the full suite.
    assert checks.check(tmp_path, [], runner=run) == 0
    assert len(calls) == 2
    assert checks.check(tmp_path, ['tests/test_one.py'], runner=run) == 0
    assert checks.check(tmp_path, [], runner=run) == 0
    assert len(calls) == 3  # A targeted success preserves an existing full pass.
    checks.check(tmp_path, [], force=True, runner=run)
    assert len(calls) == 4
    checks.check(tmp_path, ['tests/test_one.py'], runner=lambda *a, **k: SimpleNamespace(returncode=1))
    checks.check(tmp_path, [], runner=run)
    assert len(calls) == 5
    (tmp_path / 'src/rgpdf/__init__.py').write_text('__version__ = "different"', encoding='utf-8')
    with pytest.raises(ValueError, match='versions must agree'):
        checks.check(tmp_path, [], runner=run)


def test_filtered_runs_and_changes_during_tests_do_not_certify_full_suite(tmp_path, monkeypatch):
    project(tmp_path)
    monkeypatch.setattr(checks, 'environment', lambda: {})
    monkeypatch.setenv('PYTEST_ADDOPTS', '-k one')
    result = SimpleNamespace(returncode=0)
    checks.check(tmp_path, [], runner=lambda *a, **k: result)
    assert not (tmp_path / '.pytest_cache/rgpdf/full-pass.json').exists()
    monkeypatch.delenv('PYTEST_ADDOPTS')
    def change(*args, **kwargs):
        (tmp_path / 'src/rgpdf/change.py').write_text('changed = 1', encoding='utf-8')
        return result
    assert checks.check(tmp_path, [], runner=change) == 1


@pytest.fixture
def source_project(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    root.mkdir()
    archive = b'original source archive'
    digest = hashlib.sha256(archive).hexdigest()
    (root / 'third-party-sources.toml').write_text(
        'pymupdf_version="1"\npyside6_version="2"\n[[archive]]\nname="Example"\n'
        f'filename="example.tar.gz"\nurl="https://example.invalid/source"\nsha256="{digest}"\n', encoding='utf-8')
    packages = {'pymupdf': '1', 'pyside6': '2', 'pyside6-addons': '2', 'pyside6-essentials': '2', 'shiboken6': '2'}
    (root / 'uv.lock').write_text('\n'.join(f'[[package]]\nname="{name}"\nversion="{version}"' for name, version in packages.items()), encoding='utf-8')
    monkeypatch.setattr(sources, 'PROJECT_ROOT', root)
    calls = []
    def download(url, destination, sha):
        calls.append(url)
        destination.write_bytes(archive)
        assert sources.sha256_file(destination) == sha
    monkeypatch.setattr(sources, 'download', download)
    return root, calls


def test_source_cache_reuses_across_versions_and_rebuilds_corruption(source_project, tmp_path):
    root, calls = source_project
    cache, output = tmp_path / 'cache', tmp_path / 'out'
    def build(version):
        return sources.main(['--project-version', version, '--output-dir', str(output), '--cache-dir', str(cache)])
    assert build('1.0.0') == 0
    assert build('1.0.1') == 0
    assert len(calls) == 1
    assert (output / 'rgpdf-1.0.1-third-party-sources.tar.gz').read_bytes() == (cache / 'sources.tar.gz').read_bytes()
    (cache / 'sources.tar.gz').write_bytes(b'corrupt gzip')
    assert build('1.0.2') == 0
    assert len(calls) == 2
    (root / 'uv.lock').write_text('[[package]]\nname="pymupdf"\nversion="wrong"', encoding='utf-8')
    with pytest.raises(SystemExit, match='stale'):
        build('1.0.3')  # A valid cache cannot bypass lock/manifest validation.


@pytest.mark.parametrize('kind', ['digest', 'missing', 'symlink', 'extra'])
def test_cached_sources_reject_bad_members(source_project, tmp_path, kind):
    root, _ = source_project
    import tomllib
    manifest_path = root / 'third-party-sources.toml'
    manifest = tomllib.loads(manifest_path.read_text(encoding='utf-8'))
    bundle = tmp_path / 'bad.tar.gz'
    with tarfile.open(bundle, 'w:gz') as tar:
        if kind == 'missing':
            pass
        else:
            entry = tarfile.TarInfo('third-party-sources/example.tar.gz' if kind != 'extra' else '../../outside')
            if kind == 'symlink':
                entry.type = tarfile.SYMTYPE
                entry.linkname = '/outside'
                tar.addfile(entry)
            else:
                entry.size = 3
                tar.addfile(entry, io.BytesIO(b'bad'))
    with pytest.raises(ValueError):
        sources.validate_bundle(bundle, manifest_path, manifest)


@pytest.fixture
def release(monkeypatch):
    value = releases.Release('owner/repo', 'v1.0.0', 'a' * 40)
    data = {'draft': True, 'body': value.marker, 'assets': []}
    calls = []
    monkeypatch.setattr(value, 'verify_tag', lambda: None)
    monkeypatch.setattr(value, 'api', lambda *a, **k: data)
    monkeypatch.setattr(value, 'gh', lambda *a, **k: calls.append(a))
    return value, data, calls


def test_release_remains_draft_until_every_asset_is_ready(release):
    value, data, calls = release
    with pytest.raises(ValueError, match='incomplete'):
        value.publish()
    assert not calls
    data['assets'] = [{'name': name, 'size': 10, 'state': 'uploaded'} for name in releases.expected_assets('1.0.0')]
    data['assets'][0]['state'] = 'new'
    with pytest.raises(ValueError):
        value.publish()
    data['assets'][0]['state'] = 'uploaded'
    value.publish()
    assert calls == [('release', 'edit', 'v1.0.0', '--draft=false', '--latest')]


def test_release_upload_is_idempotent_only_for_owned_drafts(release, tmp_path):
    value, data, calls = release
    license = tmp_path / 'LICENSE'
    license.write_text('license', encoding='utf-8')
    value.upload([license])
    assert calls[-1][-1] == '--clobber'
    data['draft'] = False
    with pytest.raises(ValueError, match='immutable'):
        value.upload([license])
    data['draft'] = True
    data['body'] = 'unrelated draft'
    with pytest.raises(ValueError, match='not prepared'):
        value.upload([license])


def test_tag_is_checked_again_before_publish(monkeypatch):
    value = releases.Release('owner/repo', 'v1.0.0', 'a' * 40)
    monkeypatch.setattr(value, 'api', lambda *a, **k: {'object': {'type': 'commit', 'sha': 'b' * 40}})
    with pytest.raises(ValueError, match='tested commit'):
        value.publish()


def test_prepare_creates_bilingual_draft_and_resumes_only_that_commit(tmp_path, monkeypatch):
    value = releases.Release('owner/repo', 'v1.0.0', 'a' * 40)
    for name in ('CHANGELOG.md', 'CHANGELOG.zh-TW.md'):
        (tmp_path / name).write_text('## 1.0.0 — 2026-11-09\n\n- Release notes\n', encoding='utf-8')
    for name in ('LICENSE', 'THIRD-PARTY-NOTICES.md'):
        (tmp_path / name).write_text('license', encoding='utf-8')
    data = None
    calls = []
    monkeypatch.setattr(value, 'verify_tag', lambda: None)
    monkeypatch.setattr(value, 'api', lambda *a, **k: data)
    def gh(*args, **kwargs):
        nonlocal data
        calls.append(args)
        if args[:2] == ('release', 'create'):
            notes = Path(args[-1]).read_text(encoding='utf-8')
            assert '繁體中文' in notes and 'English' in notes and value.marker in notes
            assert '--draft' in args and '--verify-tag' in args
            data = {'draft': True, 'body': notes}
    monkeypatch.setattr(value, 'gh', gh)
    value.prepare(tmp_path)
    value.prepare(tmp_path)
    assert len([call for call in calls if call[:2] == ('release', 'create')]) == 1
    assert len([call for call in calls if call[:2] == ('release', 'upload')]) == 2
    data['draft'] = False
    with pytest.raises(ValueError, match='already published'):
        value.prepare(tmp_path)


def test_startup_waits_for_gui_not_just_primary_process(tmp_path):
    trace = tmp_path / 'trace.jsonl'
    process = SimpleNamespace(pid=123, poll=lambda: None)
    trace.write_text(json.dumps({'event': 'primary', 'pid': 123}) + '\n', encoding='utf-8')
    with pytest.raises(TimeoutError):
        smoke.wait_ready(process, trace, timeout=.01)
    trace.write_text(json.dumps({'event': 'gui-ready', 'pid': 123}) + '\n', encoding='utf-8')
    smoke.wait_ready(process, trace, timeout=.1)
    with pytest.raises(RuntimeError, match='exited'):
        smoke.wait_ready(SimpleNamespace(pid=123, poll=lambda: 1), trace)
