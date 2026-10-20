# rgPDF

[繁體中文](README.md) · English

rgPDF is a cross-platform desktop application for searching text-layer PDFs and Word documents with plain text or regular expressions. Matches appear as they are found and can be opened in an asynchronous page preview with precise, configurable highlighting.

The **rg** in its name pays homage to the text-search tool **ripgrep**.

## Features

- Search PDFs, Word documents (`.doc` and `.docx`), or both in a folder, optionally including subfolders.
- Plain-text and regular-expression modes with optional case sensitivity.
- Matches across lines and page boundaries, including line-end dehyphenation.
- Incremental per-match results without blocking the interface.
- Three coordinated views for files, matching passages, and PDF page preview.
- Per-character highlight geometry and configurable highlight colors.
- English and Traditional Chinese interfaces, plus system/light/dark themes.
- Persistent search and appearance preferences.

rgPDF searches existing PDF text layers. Searching Word documents requires Microsoft Word (Windows) or LibreOffice; documents are converted to cached PDFs for text search and page preview. rgPDF never runs document macros, does not perform OCR, and does not modify source files.

Word search uses three independent stages: directly screen DOCX text, enqueue a PDF conversion on the first possible hit while screening other files, then search each ready PDF for all official matches. Page numbers, counts, context, and highlights come exclusively from the PDF. Valid PDF caches bypass screening. Screening is conservative about layout differences: regex operators, legacy `.doc`, dynamic fields or unsupported content, and extraction failures go directly through PDF search. Selecting a folder does not convert documents. Cancelling search stops screening and queued conversions; an active export is cleaned up after it completes or returns.

The **Ignore layout line wraps** button beside Regex is off by default. When enabled, text blocks, adjacent-line geometry, and detected table cells guide joining: `循環` followed by `緩衝區` on the next line matches `循環緩衝區`; `buffer` / `size` retains a word space, and `inter-` / `national` removes the wrap hyphen. Actual spaces within lines are preserved. Paragraphs, columns, and different cells are not deliberately joined; page boundaries retain a space. Regex runs on this normalized text, while preview highlights retain each original character location. The setting is saved.

## Usage

Choose a folder with **Browse**, enter text or a regular expression, and click
**Search**. Select a file and matching passage to preview its page and highlight.

The **Filename stem filter** below **Document folder** optionally limits which files are searched. Click the help icon immediately to the left of its input field to view syntax explanations and examples. Leave it empty for no filter. It matches the entire filename without its last extension, ignoring case, and supports `*` (any string), `?` (one character), `[abc]`, `[0-9]`, and `[!abc]`. For example, `ch0*` includes `ch01.pdf` and `ch02.docx` but excludes `ch1.pdf` and `ch2.docx`; `ch01` matches that exact stem. The filter applies before PDF reading or Word conversion and works together with file-type and subfolder settings. It is saved between sessions and is independent of the text search’s regex and case settings.

Use the preview’s Previous page / Next page buttons to browse all document pages, including pages without a match. Select another passage in the match pane to jump to its matched page. **Fit page** scales the whole page to the preview’s width and height and adapts when the pane is resized; **Fit width** remains available for reading at a larger size.
The toolbar controls below are listed in their on-screen order. Hover over a
button to see its current setting; clicking a three-state button cycles modes.

| Toolbar icon | Control | Usage |
| --- | --- | --- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/recursive.png"><img src="docs/toolbar/recursive.png" width="34" height="34" alt="Nested folders"></picture> | Include subfolders | Toggle recursive folder search. |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/scope_pdf.png"><img src="docs/toolbar/scope_pdf.png" width="34" height="34" alt="PDF"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/scope_word.png"><img src="docs/toolbar/scope_word.png" width="34" height="34" alt="Word"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/scope_all.png"><img src="docs/toolbar/scope_all.png" width="34" height="34" alt="PDF and Word"></picture> | File types | Cycle PDF → Word (DOC/DOCX) → both. Word requires Microsoft Word on Windows or LibreOffice. |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/case.png"><img src="docs/toolbar/case.png" width="34" height="34" alt="Aa"></picture> | Case sensitive | Toggle case-sensitive matching. |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/regex.png"><img src="docs/toolbar/regex.png" width="34" height="34" alt="Regular expression"></picture> | Regular expression | Toggle regex; use the help icon beside the search field for examples. |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/line_wrap.png"><img src="docs/toolbar/line_wrap.png" width="34" height="34" alt="Line wrap"></picture> | Ignore layout line wraps | Join adjacent CJK lines, preserve English word spaces and original highlights; off by default. |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/highlighter.png"><img src="docs/toolbar/highlighter.png" width="34" height="34" alt="Highlighter"></picture> | Highlight color | Choose a preset or custom color. |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/cache.png"><img src="docs/toolbar/cache.png" width="34" height="34" alt="Trash can"></picture> | Clear Word cache | Confirm deletion of conversion PDFs; original Word files are preserved. Disabled during search. |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/language_system.png"><img src="docs/toolbar/language_system.png" width="34" height="34" alt="System language"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/language_zh.png"><img src="docs/toolbar/language_zh.png" width="34" height="34" alt="Chinese"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/language_en.png"><img src="docs/toolbar/language_en.png" width="34" height="34" alt="English"></picture> | Language | Cycle system → Traditional Chinese → English. |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/theme_system.png"><img src="docs/toolbar/theme_system.png" width="34" height="34" alt="System theme"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/sun.png"><img src="docs/toolbar/sun.png" width="34" height="34" alt="Light theme"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/moon.png"><img src="docs/toolbar/moon.png" width="34" height="34" alt="Dark theme"></picture> | Color theme | Cycle system → light → dark. |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/about.png"><img src="docs/toolbar/about.png" width="34" height="34" alt="Information"></picture> | About | View version, license, and source links. |

Hover over an icon to see its action. Search, color, and preview controls:

| Icon | Tooltip / action |
| --- | --- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/browse.png"><img src="docs/toolbar/browse.png" width="34" height="34" alt="Browse…"></picture> | Browse… |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/search.png"><img src="docs/toolbar/search.png" width="34" height="34" alt="Search"></picture> | Search |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/cancel.png"><img src="docs/toolbar/cancel.png" width="34" height="34" alt="Cancel"></picture> | Cancel |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/help.png"><img src="docs/toolbar/help.png" width="34" height="34" alt="Search pattern help"></picture> | Search pattern help |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/custom_color.png"><img src="docs/toolbar/custom_color.png" width="34" height="34" alt="Custom color…"></picture> | Custom color… |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/previous_page.png"><img src="docs/toolbar/previous_page.png" width="34" height="34" alt="Previous page"></picture> | Previous page |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/next_page.png"><img src="docs/toolbar/next_page.png" width="34" height="34" alt="Next page"></picture> | Next page |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/zoom_out.png"><img src="docs/toolbar/zoom_out.png" width="34" height="34" alt="Zoom out"></picture> | Zoom out |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/zoom_in.png"><img src="docs/toolbar/zoom_in.png" width="34" height="34" alt="Zoom in"></picture> | Zoom in |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/fit_width.png"><img src="docs/toolbar/fit_width.png" width="34" height="34" alt="Fit width"></picture> | Fit width |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/toolbar/dark/fit_page.png"><img src="docs/toolbar/fit_page.png" width="34" height="34" alt="Fit page"></picture> | Fit page |

Search settings are saved between sessions. Conversion cache is cleaned at
startup: entries unused for 30 days expire, then the oldest entries are removed
if total size exceeds 500 MB. Use **Cancel** to stop a search.

## Install the latest release

### Windows standalone download

Download the versioned `rgpdf-*-windows-x86_64.exe` and its `.sha256` file
from the [latest GitHub Release](https://github.com/codemee/rgpdf/releases/latest).
The executable is currently unsigned, so Windows SmartScreen may show an
unknown-publisher warning. Verify that the SHA-256 value matches the published
file before choosing to run it.

No Python or uv installation is required for the standalone executable. PDF search has no additional requirement. Word search requires an existing Microsoft Word installation on Windows or an existing LibreOffice installation.

### macOS App (Apple Silicon)

Download the versioned `rgpdf-*-macos-arm64.dmg` and its `.sha256` file from
the [latest GitHub Release](https://github.com/codemee/rgpdf/releases/latest).
Verify the download first:

```shell
shasum -a 256 rgpdf-*-macos-arm64.dmg
```

After confirming that the output matches the `.sha256` file, open the DMG and
drag `rgpdf.app` to Applications. This build supports Apple Silicon (M-series)
Macs and does not require Python or uv.

The App is ad-hoc signed and not notarized by Apple. If macOS blocks its first
launch, Control-click `rgpdf` in Finder's Applications folder, choose Open,
then choose Open again in the confirmation dialog.

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

After toolbar artwork changes, regenerate the README images with
`uv run python scripts/generate_toolbar_icons.py`.

See [Technical details](docs/TECHNICAL.md) for architecture, matching semantics, concurrency, and release engineering. Version history is in the [changelog](CHANGELOG.md).

## Releases

[GitHub Releases](https://github.com/codemee/rgpdf/releases/latest) provide Windows executables, macOS Apps, SHA-256 checksums, and corresponding source archives. Python packages are available on PyPI. The `latest` Git tag points to the newest published source release.

See [Technical details](docs/TECHNICAL.md#release-process) for the release workflow and maintenance instructions.

## License

rgPDF is licensed under the [GNU Affero General Public License version 3](LICENSE).
You may use, study, modify, and redistribute it under the terms of that license.
Distributed binaries must be accompanied by the complete corresponding source
for the same version.

This application uses PyMuPDF/MuPDF under AGPLv3 and PySide6/Qt under LGPLv3.
See [third-party notices](THIRD-PARTY-NOTICES.md) and the
[release compliance checklist](docs/RELEASING.zh-TW.md).
