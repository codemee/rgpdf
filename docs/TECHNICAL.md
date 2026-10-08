# rgpdf technical details

[繁體中文](TECHNICAL.zh-TW.md) · English

## Technology and module boundaries

rgpdf targets Python 3.12–3.13 and is managed by uv. PySide6 provides the desktop UI, PyMuPDF extracts and renders PDF content, and the third-party `regex` package provides Unicode-aware matching with per-document timeouts. Windows builds use pywin32 to request fixed-format export from an existing Microsoft Word installation.

| Module | Responsibility |
| --- | --- |
| `app.py` | QApplication lifecycle, palettes, flat styling, and application startup |
| `main_window.py` | Search controls, settings toolbar, incremental result models, and view coordination |
| `search.py` | File discovery, conversion routing, PDF extraction, normalization, matching, and coordinate mapping |
| `word_conversion.py` | Word/LibreOffice conversion selection and local PDF cache |
| `worker.py` | Background search runnable and cross-thread Qt signals |
| `preview.py` | Asynchronous page rendering, stale-request rejection, zoom, and highlighting |
| `models.py` | Immutable search options, results, page highlights, and extraction mappings |
| `i18n.py` | English and Traditional Chinese string catalogs |
| `resources.py` | Packaged application artwork lookup |

The search core has no dependency on UI widgets. It can be exercised directly by tests or another Python caller.

## Search pipeline

1. `discover_documents` enumerates the file types selected by `SearchOptions.search_scope` in stable relative-path order. Recursion is controlled by `SearchOptions.recursive`.
2. Word documents are converted to a cache under the user's local cache directory. Microsoft Word is preferred on Windows; LibreOffice is the fallback. Cache identity includes the source path, size, modification time, and converter. Macros and automatic external-link updates are disabled, and sources are opened read-only. At startup, entries unused for 30 days are removed and least-recently-used entries are evicted until the cache is no larger than 500 MB. A toolbar action can clear all Word conversion cache while no search is active.
3. Each resulting PDF is opened independently. Password-protected, corrupt, empty, textless, and unconvertible files become non-fatal warnings.
4. Each page is extracted with PyMuPDF `rawdict`. `TEXT_PRESERVE_IMAGES` is explicitly disabled so image payloads are never decoded during text search.
5. Text blocks, lines, spans, and characters are traversed in reading order. Every visible character retains its page index and exact bounding box.
6. Whitespace within a line is collapsed, ordinary line and page boundaries become spaces, and a line-ending hyphen is removed before joining the next line.
7. The complete normalized document is searched. Plain text is escaped before compilation; regular expressions use Unicode `VERSION1`, optional full case folding, and a per-document timeout.
8. Zero-width matches are ignored. Each non-empty match is mapped back to the bounding boxes of only the characters it covers.
9. Match context is bounded by the nearest CJK or ASCII punctuation (`，。！？；：、,.!?;:`), with a limited-radius fallback when punctuation is absent.

The normalized text string and `CharacterRef` tuple always have identical lengths. Synthetic separators have a page reference but no rectangle, so expressions can cross pages without producing artificial highlights.

## Incremental results and concurrency

`SearchWorker` runs `search_folder` in Qt's global thread pool. The core calls a match callback immediately after constructing each `TextMatch`; the worker forwards it through `match_found`. The main thread appends the row, updates the containing file's count, and leaves existing selection intact.

Preview rendering is separate from search work. Each selection creates a `PreviewRenderWorker` that opens its own document handle, renders one page to a `QImage`, and paints translucent highlight rectangles off the UI thread. A monotonically increasing request ID ensures results from older selections or resize requests are discarded. Only conversion to `QPixmap` and widget updates occur on the UI thread.

Cancellation uses a thread-safe event checked between documents. Regex execution has its own timeout to contain catastrophic backtracking. Closing the window invalidates pending preview requests and requests search cancellation.

## UI and persisted settings

The main window uses a top settings toolbar and a horizontal splitter:

- Left: folder/pattern controls above file and match result tables. A three-state toolbar button selects PDF, Word, or combined discovery.
- Right: full-height PDF preview with matched-page navigation, fit-to-width, and zoom.

Settings use `QSettings("rgpdf", "rgpdf")`:

| Key | Meaning |
| --- | --- |
| `appearance/language` | `system`, `zh_TW`, or `en` |
| `appearance/theme` | `system`, `light`, or `dark` |
| `appearance/highlight_color` | Highlight color as `#rrggbb` |
| `search/folder` | Last selected folder |
| `search/pattern` | Last search pattern |
| `search/use_regex` | Regular-expression mode |
| `search/case_sensitive` | Case-sensitive matching |
| `search/recursive` | Include subfolders |
| `search/scope` | `pdf`, `word`, or `all` |
| `window/geometry` | Window geometry |
| `window/main_splitter` | Left/preview split |
| `window/result_splitter` | File/match split |

Language and theme buttons cycle through their three modes. Toggle settings use neutral checked styling. The highlight button draws only the marker glyph in the selected color; its palette offers presets and a native `QColorDialog`.

## Testing and packaging

The test suite covers literal and regex matching, case behavior, cross-page mapping, dehyphenation, punctuation context, corrupt/textless PDFs, per-match callbacks, settings persistence, theme switching, packaged SVG loading, and asynchronous preview rendering.

```shell
uv sync
uv run pytest
uv build
```

`uv build` produces an sdist and wheel. The SVG application icon lives inside the Python package so both editable and built installations can resolve it through `importlib.resources`.

## Release process

1. Set the same version in `pyproject.toml` and `src/rgpdf/__init__.py`.
2. Update both changelogs and both README/technical-document variants when behavior changes.
3. Run tests locally and launch `uv run rgpdf` for manual testing. Executable builds run only remotely.
4. Commit and push `main`, then create and push the immutable `vX.Y.Z` tag.
5. The tag push runs `.github/workflows/publish-pypi.yml`, tests and builds Windows/macOS artifacts remotely, creates the GitHub Release, and publishes to PyPI through Trusted Publishing.
6. Move the `latest` source tag to the same commit after the release workflow succeeds.

Install documentation must use PyPI's latest release or the moving `latest` source tag, never a hard-coded version tag. Immutable version tags remain available for reproducible source checkout and release history. The PyPI project must trust repository `codemee/rgpdf`, workflow `publish-pypi.yml`, and environment `pypi`; no long-lived upload token is stored in GitHub.
