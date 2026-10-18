# rgPDF technical details

[繁體中文](TECHNICAL.zh-TW.md) · English

## Technology and module boundaries

rgPDF targets Python 3.12–3.13 and is managed by uv. PySide6 provides the desktop UI, PyMuPDF extracts and renders PDF content, and the third-party `regex` package provides Unicode-aware matching with per-document timeouts. Windows builds use pywin32 to request fixed-format export from an existing Microsoft Word installation.

| Module | Responsibility |
| --- | --- |
| `app.py` | QApplication lifecycle, palettes, flat styling, and application startup |
| `buttons.py` | Shared palette-aware vector action buttons, localized tooltips, and accessible names |
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

1. `discover_documents` enumerates the file types selected by `SearchOptions.search_scope` in stable relative-path order. Recursion is controlled by `SearchOptions.recursive`. `SearchOptions.stem_glob` optionally filters the complete `Path.stem` (only the final extension is removed) with case-folded `fnmatchcase` glob matching. Empty means no filter. This filter also applies to explicitly supplied `paths` before reading or conversion, so progress and scanned counts include only eligible files. It is independent of content regex/case settings and never matches parent directories.
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

The default `README.md` is Traditional Chinese, so GitHub and the package readme open in Traditional Chinese. English is maintained in `README.en.md`; `README.zh-TW.md` stays identical to the default README for existing links. All three README files are included in source distributions.

## UI and persisted settings

The main window uses a top settings toolbar and a horizontal splitter:

- Left: folder, filename-stem filter, and pattern controls above file and match result tables. A three-state toolbar button selects PDF, Word, or combined discovery.
- Right: full-height PDF preview with previous/next navigation through every document page, fit-to-width, fit-to-page, and zoom.

The official display name is rgPDF. The command, Python package, cache paths, and settings identifiers remain `rgpdf`. Selecting a match opens its start page; preview arrows browse adjacent pages, including pages without matches, and are disabled at document boundaries. Highlights remain tied to the selected match. Fit-to-page uses the smaller of the available viewport width/page width and height/page height ratios, without the manual zoom minimum, so even large pages fit completely. Both fit modes recompute on pane resize and page navigation; manual zoom exits either fit mode.

Result tables disable the header’s default last-section stretching so per-column resize modes apply: file counts size to contents and filenames use the remaining width.

Settings use `QSettings("rgpdf", "rgpdf")`:

| Key | Meaning |
| --- | --- |
| `appearance/language` | `system`, `zh_TW`, or `en` |
| `appearance/theme` | `system`, `light`, or `dark` |
| `appearance/highlight_color` | Highlight color as `#rrggbb` |
| `search/folder` | Last selected folder |
| `search/stem_glob` | Filename-stem glob filter; empty means no filter |
| `search/pattern` | Last search pattern |
| `search/use_regex` | Regular-expression mode |
| `search/case_sensitive` | Case-sensitive matching |
| `search/recursive` | Include subfolders |
| `search/scope` | `pdf`, `word`, or `all` |
| `window/geometry` | Window geometry |
| `window/main_splitter` | Left/preview split |
| `window/result_splitter` | File/match split |

The filename-stem and search-pattern help icons align vertically immediately to the left of their input fields and share a rich-text help popup implementation with localized syntax explanations and examples. Icon outlines use the shared `SettingsButton.STROKE_WIDTH` of 1 logical px, including PDF badge outlines. Action buttons share a 34×34 px footprint, 4 px padding, and 4 px control spacing across panes; circular color swatches retain their 28×28 px size. `SettingsToolBar` reapplies shared spacing and symmetric 4 px margins after Qt polish, show, and style-change events. The toolbar remains 42 px high (34 px buttons plus 4 px above and below), including after theme changes. Toolbar glyphs use small vertical offsets for asymmetric artwork so their visible centers align with language and theme icons. Language and theme buttons cycle through their three modes. Toggle settings use neutral checked styling. The highlight button draws only the marker glyph in the selected color; its palette offers presets and a native `QColorDialog`.

README icons are exported by `uv run python scripts/generate_toolbar_icons.py`: light images stay in `docs/toolbar/`, and dark images are in `docs/toolbar/dark/`. Both variants render the shared button painter with the theme’s higher-contrast text color and an opaque base-color tile at 2× resolution (68×68 px, displayed at 34×34 px). README `<picture>` elements use `prefers-color-scheme: dark` to select dark assets and keep a readable light fallback for viewers that ignore source selection.

## Testing and packaging

The test suite covers literal and regex matching, case behavior, cross-page mapping, dehyphenation, punctuation context, corrupt/textless PDFs, per-match callbacks, settings persistence, theme switching, packaged SVG loading, and asynchronous preview rendering.

```shell
uv sync
uv run pytest
uv build
```

`uv build` produces an sdist and wheel. The SVG application icon uses an equal-width/height silhouette with balanced margins, retaining the blue folded-document and `.*` mark. It lives inside the Python package so both editable and built installations can resolve it through `importlib.resources`.

## Release process

1. Set the same version in `pyproject.toml` and `src/rgpdf/__init__.py`.
2. Update both changelogs and both README/technical-document variants when behavior changes.
3. Run tests locally and launch `uv run rgpdf` for manual testing. Executable builds run only remotely.
4. Commit and push `main`, then create and push the immutable `vX.Y.Z` tag.
5. The tag push runs `.github/workflows/publish-pypi.yml`, tests and builds Windows/macOS artifacts remotely, creates the GitHub Release, and publishes to PyPI through Trusted Publishing.
6. Move the `latest` source tag to the same commit after the release workflow succeeds.

Install documentation must use PyPI's latest release or the moving `latest` source tag, never a hard-coded version tag. Immutable version tags remain available for reproducible source checkout and release history. The PyPI project must trust repository `codemee/rgpdf`, workflow `publish-pypi.yml`, and environment `pypi`; no long-lived upload token is stored in GitHub.
