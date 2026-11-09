# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Upload verified build outputs to one draft, then publish only a complete release."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def expected_assets(version: str) -> set[str]:
    files = {'LICENSE', 'THIRD-PARTY-NOTICES.md'}
    for suffix in ('windows-x86_64.zip', 'macos-arm64.dmg', 'source.tar.gz', 'third-party-sources.tar.gz'):
        name = f'rgpdf-{version}-{suffix}'
        files.update((name, name + '.sha256'))
    return files


class Release:
    def __init__(self, repo: str, tag: str, sha: str):
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
            raise ValueError('Expected owner/repository')
        if not re.fullmatch(r'v\d+\.\d+\.\d+', tag) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', sha):
            raise ValueError('Expected a version tag and full commit SHA')
        self.repo, self.tag, self.sha = repo, tag, sha
        self.version = tag[1:]
        self.marker = f'<!-- rgpdf-release-sha:{sha} -->'

    def gh(self, *args, missing_ok=False):
        result = subprocess.run(['gh', *args], text=True, encoding='utf-8', capture_output=True,
                                env={**os.environ, 'GH_REPO': self.repo})
        if result.returncode:
            if missing_ok and '(HTTP 404)' in result.stderr:
                return None
            raise RuntimeError(result.stderr.strip() or 'GitHub CLI failed')
        return result.stdout

    def api(self, path, *, missing_ok=False):
        result = self.gh('api', f'repos/{self.repo}/{path}', missing_ok=missing_ok)
        return json.loads(result) if result is not None else None

    def verify_tag(self):
        obj = self.api(f'git/ref/tags/{self.tag}')['object']
        for _ in range(8):
            if obj['type'] == 'commit':
                if obj['sha'] != self.sha:
                    raise ValueError('Release tag no longer points at the tested commit')
                return
            if obj['type'] != 'tag':
                break
            obj = self.api('git/tags/' + obj['sha'])['object']
        raise ValueError('Could not resolve the version tag to a commit')

    def current(self, *, missing_ok=False):
        release = self.api(f'releases/tags/{self.tag}', missing_ok=missing_ok)
        if release is not None and self.marker not in (release.get('body') or ''):
            raise ValueError('Refusing to change a release not prepared for this commit')
        return release

    def require_draft(self):
        self.verify_tag()
        release = self.current()
        if not release['draft']:
            raise ValueError('Published releases are immutable; no assets were changed')
        return release

    def prepare(self, root: Path):
        self.verify_tag()
        existing = self.current(missing_ok=True)
        if existing is not None:
            if not existing['draft']:
                raise ValueError('This version is already published')
        else:
            parts = []
            for filename, label in (('CHANGELOG.zh-TW.md', '繁體中文'), ('CHANGELOG.md', 'English')):
                text = (root / filename).read_text(encoding='utf-8')
                section = re.search(rf'^## {re.escape(self.version)}\b[^\n]*\n(.*?)(?=^## |\Z)',
                                    text, re.MULTILINE | re.DOTALL)
                if section is None:
                    raise ValueError(f'Missing {self.version} notes in {filename}')
                parts.append(f'### {label}\n\n{section[1].strip()}')
            notes = '\n\n'.join(parts) + '\n\n' + self.marker + '\n'
            with tempfile.TemporaryDirectory(prefix='rgpdf-release-notes-') as directory:
                path = Path(directory) / 'notes.md'
                path.write_text(notes, encoding='utf-8')
                self.gh('release', 'create', self.tag, '--draft', '--verify-tag', '--target', self.sha,
                        '--title', f'rgPDF {self.version}', '--notes-file', str(path))
        self.upload([root / 'LICENSE', root / 'THIRD-PARTY-NOTICES.md'])

    def upload(self, files: list[Path]):
        self.require_draft()
        names = [file.name for file in files]
        if not files or len(set(names)) != len(names) or not set(names) <= expected_assets(self.version):
            raise ValueError('Unexpected or duplicate release asset names')
        if any(not file.is_file() or file.stat().st_size == 0 for file in files):
            raise ValueError('Missing or empty release assets')
        self.gh('release', 'upload', self.tag, *(str(file) for file in files), '--clobber')

    def publish(self):
        self.verify_tag()
        release = self.current()
        assets = release['assets']
        names = [item['name'] for item in assets]
        if (set(names) != expected_assets(self.version) or len(names) != len(set(names))
                or any(item['state'] != 'uploaded' or item['size'] <= 0 for item in assets)):
            raise ValueError('Release assets are incomplete or unexpected; draft remains unpublished')
        if release['draft']:
            self.gh('release', 'edit', self.tag, '--draft=false', '--latest')
        print(f'Published {self.tag} from {self.sha}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'upload', 'publish'))
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--tag', required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--files', nargs='+', type=Path)
    args = parser.parse_args(argv)
    if not args.repo:
        parser.error('--repo or GITHUB_REPOSITORY is required')
    release = Release(args.repo, args.tag, args.sha)
    if args.operation == 'prepare':
        release.prepare(Path(__file__).resolve().parents[1])
    elif args.operation == 'upload':
        release.upload(args.files or [])
    else:
        release.publish()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
