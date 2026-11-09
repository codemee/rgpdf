# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import argparse
import gzip
import hashlib
import shutil
import tarfile
import tempfile
import tomllib
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def locked_version(lock_text: str, package_name: str) -> str:
    lock = tomllib.loads(lock_text)
    matches = [item["version"] for item in lock["package"] if item["name"] == package_name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one locked {package_name} package, found {len(matches)}")
    return matches[0]


def download(url: str, destination: Path, expected_sha256: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "rgpdf-source-packager/1"})
    digest = hashlib.sha256()
    print(f"Downloading {destination.name}", flush=True)
    with urllib.request.urlopen(request) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected_sha256:
        destination.unlink()
        raise RuntimeError(f"SHA-256 mismatch for {destination.name}: expected {expected_sha256}, got {actual}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def source_readme(manifest: dict) -> bytes:
    lines = [
        "rgpdf corresponding third-party sources", "",
        "These unmodified upstream archives correspond to the native libraries in uv.lock.",
        "Each download is verified before packaging against the pinned SHA-256 below.", "",
    ]
    for item in manifest['archive']:
        lines.extend([item['name'], f"  File: {item['filename']}", f"  URL: {item['url']}",
                      f"  SHA-256: {item['sha256']}", ""])
    return '\n'.join(lines).encode('utf-8')


def validate_bundle(path: Path, manifest_path: Path, manifest: dict) -> None:
    """Check pinned inner hashes without extracting untrusted cache contents."""
    prefix = 'third-party-sources/'
    expected = {prefix + item['filename']: item['sha256'] for item in manifest['archive']}
    expected[prefix + manifest_path.name] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    expected[prefix + 'README.txt'] = hashlib.sha256(source_readme(manifest)).hexdigest()
    seen = set()
    with tarfile.open(path, 'r|gz') as bundle:
        for member in bundle:
            if member.name == 'third-party-sources' and member.isdir():
                continue
            if not member.isfile() or member.name not in expected or member.name in seen:
                raise ValueError(f'Unexpected cached source member: {member.name}')
            digest = hashlib.sha256()
            with bundle.extractfile(member) as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != expected[member.name]:
                raise ValueError(f'Cached source SHA-256 mismatch: {member.name}')
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError('Cached source bundle is incomplete')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "dist")
    parser.add_argument("--project-version", required=True)
    parser.add_argument("--cache-dir", type=Path, help="Optional CI source-bundle cache")
    args = parser.parse_args(argv)

    manifest_path = PROJECT_ROOT / "third-party-sources.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    lock_text = (PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8")
    expected_versions = {
        "pymupdf": manifest["pymupdf_version"],
        "pyside6": manifest["pyside6_version"],
        "pyside6-addons": manifest["pyside6_version"],
        "pyside6-essentials": manifest["pyside6_version"],
        "shiboken6": manifest["pyside6_version"],
    }
    for package, expected in expected_versions.items():
        actual = locked_version(lock_text, package)
        if actual != expected:
            raise SystemExit(
                f"third-party-sources.toml is stale: uv.lock has {package} {actual}, expected {expected}"
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"rgpdf-{args.project_version}-third-party-sources.tar.gz"
    cached = args.cache_dir / 'sources.tar.gz' if args.cache_dir else None
    if cached is not None and cached.is_file():
        try:
            validate_bundle(cached, manifest_path, manifest)
        except (OSError, ValueError, tarfile.TarError, EOFError) as exc:
            print(f'Rejecting cached sources: {exc}', flush=True)
        else:
            shutil.copyfile(cached, output)
            write_checksum(output)
            print(f'Reused verified sources: {output}', flush=True)
            return 0
    with tempfile.TemporaryDirectory(prefix="rgpdf-sources-") as temporary:
        staging = Path(temporary) / "third-party-sources"
        staging.mkdir()
        shutil.copy2(manifest_path, staging / manifest_path.name)
        for archive in manifest["archive"]:
            destination = staging / archive["filename"]
            download(archive["url"], destination, archive["sha256"])
        (staging / "README.txt").write_bytes(source_readme(manifest))

        print(f"Creating {output}", flush=True)
        with output.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                archive.add(staging, arcname=staging.name)

    write_checksum(output)
    if cached is not None:
        cached.parent.mkdir(parents=True, exist_ok=True)
        temporary = cached.with_suffix('.tmp')
        shutil.copyfile(output, temporary)
        temporary.replace(cached)
    print(f"Created {output} ({output.stat().st_size} bytes)")
    return 0


def write_checksum(output: Path) -> None:
    digest = sha256_file(output)
    checksum = output.with_name(f"{output.name}.sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="ascii")


if __name__ == "__main__":
    raise SystemExit(main())
