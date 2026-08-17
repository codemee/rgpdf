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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "dist")
    parser.add_argument("--project-version", required=True)
    args = parser.parse_args()

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
    with tempfile.TemporaryDirectory(prefix="rgpdf-sources-") as temporary:
        staging = Path(temporary) / "third-party-sources"
        staging.mkdir()
        shutil.copy2(manifest_path, staging / manifest_path.name)
        lines = [
            "rgpdf corresponding third-party sources",
            "",
            "These unmodified upstream archives correspond to the native libraries in uv.lock.",
            "Each download is verified before packaging against the pinned SHA-256 below.",
            "",
        ]
        for archive in manifest["archive"]:
            destination = staging / archive["filename"]
            download(archive["url"], destination, archive["sha256"])
            lines.extend(
                [
                    archive["name"],
                    f"  File: {archive['filename']}",
                    f"  URL: {archive['url']}",
                    f"  SHA-256: {archive['sha256']}",
                    "",
                ]
            )
        (staging / "README.txt").write_text("\n".join(lines), encoding="utf-8")

        print(f"Creating {output}", flush=True)
        with output.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                archive.add(staging, arcname=staging.name)

    digest = sha256_file(output)
    checksum = output.with_name(f"{output.name}.sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"Created {output} ({output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
