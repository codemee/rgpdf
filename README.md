# rgpdf

[繁體中文](README.zh-TW.md) · English

rgpdf is a cross-platform desktop application for searching text-layer PDFs with plain text or regular expressions. Matches appear as they are found and can be opened in an asynchronous page preview with precise, configurable highlighting.

## Features

- Search multiple PDFs in a folder, optionally including subfolders.
- Plain-text and regular-expression modes with optional case sensitivity.
- Matches across lines and page boundaries, including line-end dehyphenation.
- Incremental per-match results without blocking the interface.
- Three coordinated views for files, matching passages, and PDF page preview.
- Per-character highlight geometry and configurable highlight colors.
- English and Traditional Chinese interfaces, plus system/light/dark themes.
- Persistent search and appearance preferences.

rgpdf searches existing PDF text layers. It does not perform OCR or modify source files.

## Install the latest release

### Windows standalone download

Download the versioned `rgpdf-*-windows-x86_64.exe` and its `.sha256` file
from the [latest GitHub Release](https://github.com/codemee/rgpdf/releases/latest).
The executable is currently unsigned, so Windows SmartScreen may show an
unknown-publisher warning. Verify that the SHA-256 value matches the published
file before choosing to run it.

No Python or uv installation is required for the standalone executable.

### Install with uv

Install [uv](https://docs.astral.sh/uv/), then install the latest release from PyPI:

```shell
uv tool install rgpdf
```

Run the application:

```shell
rgpdf
```

To update an existing installation:

```shell
uv tool upgrade rgpdf
```

Windows and macOS are supported; uv manages the required Python environment.

To install the latest source release directly from GitHub instead, use the moving `latest` tag:

```shell
uv tool install "git+https://github.com/codemee/rgpdf.git@latest"
```

## Development

```shell
git clone https://github.com/codemee/rgpdf.git
cd rgpdf
uv sync
uv run pytest
uv run rgpdf
```

Build a self-contained Windows executable (Python and uv are only required on
the build machine):

```powershell
uv sync --frozen
./scripts/build-windows.ps1 -Python .venv/Scripts/python.exe
```

The result is `dist/rgpdf.exe`. GitHub Actions also publishes the executable,
`LICENSE`, and third-party notices as the `rgpdf-windows-x86_64` workflow
artifact. Public release distribution additionally requires the corresponding
source materials listed in the release compliance checklist.

See [Technical details](docs/TECHNICAL.md) for architecture, matching semantics, concurrency, and release engineering. Version history is in the [changelog](CHANGELOG.md).

## Releases

Immutable releases use version tags such as `v0.0.3`. The movable `latest` Git tag always points to the newest published source release. PyPI provides the canonical packaged release.

## License

rgpdf is licensed under the [GNU Affero General Public License version 3](LICENSE).
You may use, study, modify, and redistribute it under the terms of that license.
Distributed binaries must be accompanied by the complete corresponding source
for the same version.

This application uses PyMuPDF/MuPDF under AGPLv3 and PySide6/Qt under LGPLv3.
See [third-party notices](THIRD-PARTY-NOTICES.md) and the
[release compliance checklist](docs/RELEASING.zh-TW.md).
