# rgpdf technical details

[繁體中文](TECHNICAL.zh-TW.md) · English

## Technology and module boundaries

rgpdf targets Python 3.12–3.13 and is managed by uv. PySide6 provides the desktop UI, PyMuPDF extracts and renders PDF content, and the third-party `regex` package provides Unicode-aware matching with per-document timeouts.

| Module | Responsibility |
| --- | --- |
| `app.py` | QApplication lifecycle, palettes, flat styling, and application startup |
| `main_window.py` | Search controls, settings toolbar, incremental result models, and view coordination |
| `search.py` | File discovery, PDF extraction, normalization, matching, and coordinate mapping |
| `worker.py` | Background search runnable and cross-thread Qt signals |
| `preview.py` | Asynchronous page rendering, stale-request rejection, zoom, and highlighting |
| `models.py` | Immutable search options, results, page highlights, and extraction mappings |
| `i18n.py` | English and Traditional Chinese string catalogs |
| `resources.py` | Packaged application artwork lookup |

The search core has no dependency on UI widgets. It can be exercised directly by tests or another Python caller.

## Search pipeline

1. `discover_pdfs` enumerates `.pdf` files in stable relative-path order. Recursion is controlled by `SearchOptions.recursive`.
2. Each PDF is opened independently. Password-protected, corrupt, empty, and textless files become non-fatal warnings.
3. Each page is extracted with PyMuPDF `rawdict`. `TEXT_PRESERVE_IMAGES` is explicitly disabled so image payloads are never decoded during text search.
4. Text blocks, lines, spans, and characters are traversed in reading order. Every visible character retains its page index and exact bounding box.
5. Whitespace within a line is collapsed, ordinary line and page boundaries become spaces, and a line-ending hyphen is removed before joining the next line.
6. The complete normalized document is searched. Plain text is escaped before compilation; regular expressions use Unicode `VERSION1`, optional full case folding, and a per-document timeout.
7. Zero-width matches are ignored. Each non-empty match is mapped back to the bounding boxes of only the characters it covers.
8. Match context is bounded by the nearest CJK or ASCII punctuation (`，。！？；：、,.!?;:`), with a limited-radius fallback when punctuation is absent.

The normalized text string and `CharacterRef` tuple always have identical lengths. Synthetic separators have a page reference but no rectangle, so expressions can cross pages without producing artificial highlights.

## Incremental results and concurrency

`SearchWorker` runs `search_folder` in Qt's global thread pool. The core calls a match callback immediately after constructing each `TextMatch`; the worker forwards it through `match_found`. The main thread appends the row, updates the containing file's count, and leaves existing selection intact.

Preview rendering is separate from search work. Each selection creates a `PreviewRenderWorker` that opens its own document handle, renders one page to a `QImage`, and paints translucent highlight rectangles off the UI thread. A monotonically increasing request ID ensures results from older selections or resize requests are discarded. Only conversion to `QPixmap` and widget updates occur on the UI thread.

Cancellation uses a thread-safe event checked between documents. Regex execution has its own timeout to contain catastrophic backtracking. Closing the window invalidates pending preview requests and requests search cancellation.

## UI and persisted settings

The main window uses a top settings toolbar and a horizontal splitter:

- Left: folder/pattern controls above file and match result tables.
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
3. Run tests and `uv build`.
4. Commit to `main`, create the immutable `vX.Y.Z` tag, and publish its GitHub Release.
5. Force-move the `latest` tag to the same commit and push it with `git push origin refs/tags/latest --force`.

Install documentation must reference `latest`, never a hard-coded version tag. Immutable version tags remain available for reproducible source checkout and release history.

