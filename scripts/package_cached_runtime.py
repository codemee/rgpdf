# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Create the embedded payload/manifest; compilation happens only on CI."""

import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


def package_runtime(source: Path, output: Path) -> str:
    if not (source / "rgpdf-runtime.exe").is_file():
        raise ValueError("Missing directory runtime executable")
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    archive = output / "runtime.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=6) as zipped:
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Symlink in runtime: {path}")
            if not path.is_file():
                continue
            name = path.relative_to(source).as_posix()
            if ":" in name or "\\" in name:
                raise ValueError(f"Unsafe runtime name: {name}")
            data = path.read_bytes()
            zipped.writestr(name, data)
            entries.append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    build_id = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "runtime.json").write_text(json.dumps({"build_id": build_id, "files": entries}), encoding="utf-8")
    (output / "BundleInfo.g.cs").write_text(
        '[assembly: System.Reflection.AssemblyTitle("rgPDF")]\n'
        '[assembly: System.Reflection.AssemblyDescription("rgPDF cached runtime experiment")]\n'
        'namespace RgPdfBootstrap { internal static class BundleInfo { '
        f'public const string BuildId = "{build_id}";'
        ' } }', encoding="utf-8")
    return build_id


if __name__ == "__main__":
    print(package_runtime(Path(sys.argv[1]), Path(sys.argv[2])))
