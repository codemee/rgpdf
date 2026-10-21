# rgPDF technical details

[繁體中文](TECHNICAL.zh-TW.md) · English

## Technology and module boundaries

rgPDF targets Python 3.12–3.13 and is managed by uv. PySide6 provides the desktop UI, PyMuPDF extracts and renders PDF content, and the third-party `regex` package provides Unicode-aware matching with per-document timeouts. Windows builds use pywin32 to request fixed-format export from an existing Microsoft Word installation.

| Module | Responsibility |
| --- | --- |
| `app.py` | QApplication lifecycle, palettes, flat styling, and application startup |
| `buttons.py` | Shared palette-aware vector action buttons, localized tooltips, and accessible names |
| `progress.py` | Progress label rendering with separate track/fill text colors |
| `main_window.py` | Search controls, settings toolbar, incremental result models, and view coordination |
| `search.py` | File discovery, conversion routing, PDF extraction, normalization, matching, and coordinate mapping |
| `layout_text.py` | Layout-aware line joining with original character coordinates and cell boundaries |
| `word_screening.py` | Conservative DOCX text screening with PDF fallback for uncertainty |
| `word_conversion.py` | Word/LibreOffice conversion selection and local PDF cache |
| `worker.py` | Background search runnable and cross-thread Qt signals |
| `pdf_search_process.py` | Reusable PDF search subprocess, incremental-match IPC, and cancellation cleanup |
| `pdf_passwords.py` | Shared PDF authentication and fingerprint-keyed, session-only credentials |
| `preview.py` | Asynchronous page rendering, stale-request rejection, zoom, and highlighting |
| `models.py` | Immutable search options, results, page highlights, and extraction mappings |
| `i18n.py` | English and Traditional Chinese string catalogs |
| `resources.py` | Packaged application artwork lookup |

The search core has no dependency on UI widgets. It can be exercised directly by tests or another Python caller.

## Search pipeline

1. `discover_documents` enumerates the file types selected by `SearchOptions.search_scope` in stable relative-path order. Recursion is controlled by `SearchOptions.recursive`. `SearchOptions.stem_glob` optionally filters the complete `Path.stem` (only the final extension is removed) with case-folded `fnmatchcase` glob matching. Empty means no filter. This filter also applies to explicitly supplied `paths` before reading or conversion, so progress and scanned counts include only eligible files. It is independent of content regex/case settings and never matches parent directories.
2. Word files are screened before candidates enter a PDF conversion queue. `word_may_match` streams WordprocessingML text from DOCX, checks literal patterns across runs, and returns on the first possible hit without creating page numbers or official matches. Screening ignores case and relaxes whitespace and hyphens. Screening requires a normalized contiguous phrase rather than scattered characters. It reads body, header/footer, note, chart, and diagram content, excluding style definitions. Patterns containing regex operators, legacy `.doc`, dynamic fields, embedded objects, or parse failures bypass screening; enabling regex for a literal phrase does not bypass it. Ordinary images, numbering, and unused styles do not force conversion; drawing text is extracted too. Valid PDF caches take precedence. Conversion prefers Microsoft Word on Windows, with LibreOffice as fallback; a batch reuses a lazily started Word instance, with COM initialization, export, and cleanup on the conversion thread. Macros and link updates are disabled and sources are read-only. Cache keys include converter, source path, size, and modification time. Startup removes entries unused for 30 days and evicts by LRU down to 500 MB; manual clearing is disabled during search.
3. Each PDF is opened independently. For a protected document, `unlock_pdf` obtains a credential through the optional `password_requested(path, incorrect)` callback and validates it with `Document.authenticate()`. Wrong passwords can be retried; skipping produces a per-file warning. Only successful authentication invokes `password_accepted`, followed by normal extraction and matching. Corrupt, empty, textless, or unconvertible files remain non-fatal warnings.
4. Each page is extracted with PyMuPDF `rawdict`. `TEXT_PRESERVE_IMAGES` is explicitly disabled so image payloads are never decoded during text search.
5. Text blocks, lines, spans, and characters are traversed in reading order. Every visible character retains its page index and exact bounding box.
6. Whitespace within a line is collapsed, ordinary line and page boundaries become spaces, and a line-ending hyphen is removed before joining the next line. Optional `SearchOptions.ignore_line_wraps` is off by default. When enabled, `layout_text.py` uses RAWDICT block IDs and direction, vertical spacing, horizontal overlap, and detected cells to identify adjacent wraps on the same page. CJK boundaries omit synthetic spaces; Latin words retain one space and ASCII letter-to-letter wrap hyphens are removed. Real within-line and edge spaces remain. Separate blocks, columns, and cells use hard separators; page boundaries retain a space. Table analysis runs only on pages with vector paths; failed detection disables joining on that page. This conservative heuristic cannot reliably identify every borderless table or merged paragraph.
7. The complete normalized document is searched. Plain text is escaped before compilation; regular expressions use Unicode `VERSION1`, optional full case folding, and a per-document timeout.
8. Zero-width matches are ignored. Each non-empty match is mapped back to the bounding boxes of only the characters it covers.
9. Match summaries stop at the nearest CJK/ASCII punctuation (`，。！？；：、,.!?;:`) or paragraph/cell newline boundary. Context radius limits always apply, even when distant punctuation exists. Whitespace is collapsed to one line and summaries are capped at 160 characters, abbreviating long matched spans when necessary. Full `matched_text`, match coordinates, and PDF highlights remain intact.

The normalized text string and `CharacterRef` tuple always have identical lengths. Synthetic separators have a page reference but no rectangle, so expressions can cross pages without producing artificial highlights.

## Incremental results and concurrency

`SearchWorker` coordinates `search_folder` in Qt's global thread pool. Three stages can run concurrently: a screening thread sends candidate paths to an unbounded queue, a conversion thread exports PDFs sequentially, and the search coordinator consumes ready PDFs through a reusable spawn subprocess. Existing PDFs and valid caches bypass unfinished Word conversions. Queues contain paths and errors, never PDF contents.

The parent receives streamed matches, complete results, and per-file errors through a Pipe. One subprocess is reused per search so PDF work cannot hold Word automation's GIL; the entry point uses `multiprocessing.freeze_support()` for frozen applications. Only PDF-produced `TextMatch` objects reach the result panes: page numbers, counts, and rectangles all refer to the same PDF, without mapping DOCX offsets to PDF text. Screening may produce false positives; a candidate with no PDF hits is omitted. Ready documents can report ahead of earlier unfinished documents; matches within each PDF retain text order. The UI displays screening progress, cumulative candidate count, and active search/export filenames.

Folder selection and filter changes affect the next search without preconverting the folder. Cancellation or window closure stops screening and queued conversions, terminates the PDF search subprocess, and cleans up the conversion thread and COM after an active Word call returns. Per-file failures remain warnings and do not block subsequent documents.

Encrypted PDF authentication uses a Pipe exchange: the child requests a password with retry state, the parent supplies input, and the child acknowledges successful authentication before streaming matches. `SearchWorker` emits a `PdfPasswordRequest`; the UI responds through a nonblocking, masked `QInputDialog`. Waiting checks cancellation every 50 ms; cancellation/closure rejects the prompt and terminates the child without manipulating widgets from worker threads. The window owns `PdfPasswords`, keyed by absolute path, size, and modification time, for repeated searches and authentication of each independent preview render. Preview workers release their temporary password reference when done. Credentials never enter `SearchOptions`, result models, QSettings, warnings, or disk caches; no decrypted copy is produced. Window closure clears credentials and rejects late authentication results.

Preview rendering is separate from search work. Each selection creates a `PreviewRenderWorker` that opens its own document handle, renders one page to a `QImage`, and paints translucent highlight rectangles off the UI thread. A monotonically increasing request ID ensures results from older selections or resize requests are discarded. Only conversion to `QPixmap` and widget updates occur on the UI thread.

Cancellation uses a thread-safe event checked while waiting for IPC or document preparation, terminating the PDF search subprocess when necessary. Regex execution has its own timeout to contain catastrophic backtracking. Closing the window invalidates pending preview requests and requests search cancellation.

The default `README.md` is Traditional Chinese, so GitHub and the package readme open in Traditional Chinese. English is maintained in `README.en.md`. Both README files are included in source distributions.

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
| `search/ignore_line_wraps` | Layout-aware joining of physical line wraps; off by default |
| `search/case_sensitive` | Case-sensitive matching |
| `search/recursive` | Include subfolders |
| `search/scope` | `pdf`, `word`, or `all` |
| `window/geometry` | Window geometry |
| `window/main_splitter` | Left/preview split |
| `window/result_splitter` | File/match split |

The filename-stem and search-pattern help icons align vertically immediately to the left of their input fields and share a rich-text help popup implementation with localized syntax explanations and examples. PDF badges use light coral (`#ff9185`) in dark mode and red in light mode; the combined PDF/Word labels are staggered to avoid covering their lettering. Icon outlines use the shared `SettingsButton.STROKE_WIDTH` of 1 logical px, including PDF badge outlines. Action buttons share a 34×34 px footprint, 4 px padding, and 4 px control spacing across panes; circular color swatches retain their 28×28 px size. `SettingsToolBar` reapplies shared spacing and symmetric 4 px margins after Qt polish, show, and style-change events. The toolbar remains 42 px high (34 px buttons plus 4 px above and below), including after theme changes. Toolbar glyphs use small vertical offsets for asymmetric artwork so their visible centers align with language and theme icons. Language and theme buttons cycle through their three modes. Dark checked-state outlines are painted by `SettingsButton` as one antialiased closed rounded path, with a 0.75 px inset, a 1.5 px `CHECKED_STROKE_WIDTH`, and 7.25 px centerline radius (8 px outer radius), sharing `SettingsButton.CORNER_RADIUS` with the 8 px checked, hover, and pressed backgrounds and avoiding QSS edge/corner seams. The dark theme uses a Unit-01-inspired deep-purple palette, neon-green checked outlines/icons and selection backgrounds with dark selection text, and orange focus/link accents. Light-mode toggles keep neutral checked styling. The highlight button draws only the marker glyph in the selected color; its palette offers presets and a native `QColorDialog`.

README icons are exported by `uv run python scripts/generate_toolbar_icons.py`: light images stay in `docs/toolbar/`, and dark images are in `docs/toolbar/dark/`. Both variants render the shared button painter with the theme’s higher-contrast text color and an opaque base-color tile at 2× resolution (68×68 px, displayed at 34×34 px). README `<picture>` elements use `prefers-color-scheme: dark` to select dark assets and keep a readable light fallback for viewers that ignore source selection.

`SearchProgressBar` retains the existing track and chunk styling and paints its percentage twice: `Text` over the track and `HighlightedText` clipped to the filled area. Dark mode therefore uses dark text over neon green and light text over the unfilled track; right-to-left and inverted progress are also supported.

## Testing and packaging

Tests cover literal and regex matching, case behavior, cross-page mapping, dehyphenation, context, corrupt/textless PDFs, streamed results, settings, themes, and preview rendering. They also verify DOCX screening, unsupported-content fallback, cached-PDF bypass, separation of candidates and official results, screening during conversion, ready-PDF bypass, process reuse, and cancellation cleanup. Password tests also cover AES-encrypted PDFs with user/owner credentials, retry, per-file skip, empty opening passwords, preview navigation, session credential cleanup, and cancellation/closure while awaiting input.

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
