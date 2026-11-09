# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Run targeted tests, or reuse a full pass for identical test inputs."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def validate_versions(root: Path) -> None:
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    tree = ast.parse((root / 'src/rgpdf/__init__.py').read_text(encoding='utf-8'))
    versions = [ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)]
    lock = tomllib.loads((root / 'uv.lock').read_text(encoding='utf-8'))
    locked = [item['version'] for item in lock['package'] if item['name'] == 'rgpdf']
    if versions != [project['project']['version']] or locked != versions:
        raise ValueError('pyproject.toml, rgpdf.__version__ and uv.lock versions must agree')


def environment() -> dict:
    return {
        'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
        'machine': platform.machine(),
        'packages': sorted((dist.metadata['Name'].lower(), dist.version)
                           for dist in importlib.metadata.distributions()
                           if dist.metadata['Name'].lower() != 'rgpdf'),
        'variables': {key: value for key, value in os.environ.items()
                      if key.startswith(('QT_', 'PYTEST_', 'PYTHON', 'RGPDF_'))
                      or key in {'PATH', 'DISPLAY', 'WAYLAND_DISPLAY', 'LANG', 'LC_ALL', 'TZ', 'CI'}},
    }


def fingerprint(root: Path, env: dict) -> str:
    paths = set()
    for folder in ('src', 'tests', 'scripts', '.github/workflows'):
        paths.update(path for path in (root / folder).rglob('*') if path.is_file()
                     and not {'__pycache__', '.pytest_cache'} & set(path.parts)
                     and path.suffix not in {'.pyc', '.pyo'})
    paths.update(root / name for name in ('pyproject.toml', 'uv.lock', 'uv.toml',
                 'pytest.ini', 'setup.cfg', 'conftest.py', '.python-version',
                 'rgpdf.spec', 'rgpdf-macos.spec', 'third-party-sources.toml', 'AGENTS.md')
                 if (root / name).is_file())
    digest = hashlib.sha256(json.dumps(env, sort_keys=True).encode())
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if relative in {'pyproject.toml', 'uv.lock'}:
            value = tomllib.loads(data.decode('utf-8'))
            if relative == 'pyproject.toml':
                value['project'].pop('version', None)
            else:
                for package in value['package']:
                    if package['name'] == 'rgpdf':
                        package.pop('version', None)
            data = json.dumps(value, sort_keys=True, default=str).encode()
        elif relative == 'src/rgpdf/__init__.py':
            data = re.sub(rb'(?m)^__version__\s*=\s*["\'][^"\'\r\n]+["\']\s*$',
                          b'__version__ = "<version>"', data)
        digest.update(relative.encode() + b'\0' + data + b'\0')
    return digest.hexdigest()


def check(root: Path, targets: list[str], *, force=False, runner=subprocess.run) -> int:
    validate_versions(root)  # Always checked, including a reused full pass.
    cache = root / '.pytest_cache/rgpdf/full-pass.json'
    env = environment()
    before = fingerprint(root, env)
    reusable = not targets and not os.environ.get('PYTEST_ADDOPTS')
    try:
        previous = json.loads(cache.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        previous = {}
    if reusable and not force and previous.get('fingerprint') == before:
        print('Full tests already passed for these inputs; version consistency checked.', flush=True)
        return 0
    # A failed forced/targeted run must not leave a previously trusted pass.
    if not targets:
        cache.unlink(missing_ok=True)
    print('Running ' + ('targeted tests.' if targets else 'full tests.'), flush=True)
    result = runner([sys.executable, '-m', 'pytest', *targets], cwd=root)
    if result.returncode:
        cache.unlink(missing_ok=True)
    if result.returncode == 0 and reusable:
        if fingerprint(root, environment()) != before:
            print('Test inputs changed during the run; no full pass recorded.', file=sys.stderr)
            return 1
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix('.tmp')
        temporary.write_text(json.dumps({'fingerprint': before}), encoding='utf-8')
        temporary.replace(cache)
    return result.returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='Run even if a matching full pass exists')
    parser.add_argument('targets', nargs='*', help='Optional pytest file/node IDs; never record a full pass')
    args = parser.parse_args(argv)
    return check(ROOT, args.targets, force=args.force)


if __name__ == '__main__':
    raise SystemExit(main())
