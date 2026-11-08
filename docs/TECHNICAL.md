# rgPDF technical details

[繁體中文](TECHNICAL.zh-TW.md) · English

## Technology and module boundaries

rgPDF targets Python 3.12–3.13 and is managed by uv. PySide6 provides the desktop UI, PyMuPDF extracts and renders PDF content, and the third-party `regex` package provides Unicode-aware matching with per-document timeouts. Windows builds use pywin32 to request fixed-format export from an existing Microsoft Word installation.

| Module | Responsibility |
| --- | --- |
| `app.py` | QApplication lifecycle, palettes, flat styling, and application startup |
| `buttons.py` | Shared palette-aware vector action buttons, localized tooltips, and accessible names |
| `progress.py` | Progress label rendering with separate track/fill text colors |
| `main_window.py` | Folder tabs, session restoration, shared conversion/credentials, and global UI coordination |
| `folder_tab.py` | Independent folder controls, results, preview, and per-tab workers |
| `folder_session.py` | FolderTabState, per-tab settings and legacy defaults |
| `main_window_toolbar.py` | Shared toolbar dimensions and style updates |
| `conversion_service.py` | Application-wide FIFO conversion and shared request lifetimes |
| `word_text.py` | Preliminary DOCX matches without PDF coordinates |
| `busy_indicator.py` | Animated preview waiting state |
| `search.py` | File discovery, conversion routing, PDF extraction, normalization, matching, and coordinate mapping |
| `layout_text.py` | Layout-aware line joining with original character coordinates and cell boundaries |
| `word_screening.py` | Conservative DOCX text screening with PDF fallback for uncertainty |
| `word_conversion.py` | Word/LibreOffice conversion selection and local PDF cache |
| `word_export.py` | Background Word discovery and cache-backed batch PDF export |
| `export_dialog.py` | Export selection, destination, and filename collision validation |
| `system_menu.py` | Windows native system-menu integration |
| `context_menu.py` | Per-user Explorer verbs, Finder Quick Action generation and removal, and quoted launch commands |
| `worker.py` | Background search runnable and cross-thread Qt signals |
| `pdf_search_process.py` | Reusable PDF search subprocess, incremental-match IPC, and cancellation cleanup |
| `pdf_passwords.py` | Shared PDF authentication and fingerprint-keyed, session-only credentials |
| `preview.py` | Asynchronous page rendering, stale-request rejection, zoom, and highlighting |
| `preview_text.py` | Character geometry, mouse selection, keyboard/menu copy, and selection overlays |
| `models.py` | Immutable search options, results, page highlights, and extraction mappings |
| `i18n.py` | English and Traditional Chinese string catalogs |
| `resources.py` | Packaged application artwork lookup |

The search core has no dependency on UI widgets. It can be exercised directly by tests or another Python caller.

## Word PDF export

The export icon reuses the combined search icon's 14×14 px marks and 24×24 px overlapping footprint, reversing their positions to Word upper-left and Adobe PDF lower-right. A 1 px right-angle arrow goes down from Word's bottom edge, then turns right into PDF's left edge through the free lower-left corner without covering either logo, using theme-aware arrow colors. Disabled export marks use opaque pastel fills (Word #9cafcc, PDF #f7a39c) instead of painter opacity, so the foreground PDF fully occludes Word in the overlap. `pdf_logo(disabled=True)` caches a recolored SVG variant; active branding is unchanged. `word_export.py` provides background discovery and cache-backed export; `export_dialog.py` provides file selection, destination, and collision validation. A debounced scan uses recursion and stem-glob settings independently of content patterns and search scope, excludes `~$` lock files, and rejects stale request IDs. Directory watchers refresh the current root and directories containing listed Word files. The dialog lists relative paths with checkboxes, an output folder, and opt-in overwrite. It rejects empty selection, invalid output folders, and case-insensitive duplicate PDF names. Output is flat, retaining original stems.

Each tab excludes its own concurrent search/export, while different tabs run concurrently and share conversion through the service. Cache clearing remains application-wide and disabled during work. It checks `cached_word_pdf` first, so cached PDFs from either renderer work even without an installed converter. Missing entries use the shared fingerprint-keyed conversion API and the shared conversion service; export does not perform content screening. A complete PDF is staged in the output folder before exclusive target creation, or replacement when overwrite is selected. Exclusive creation protects against targets appearing after the initial check and does not require hard links. Failed incomplete copies are removed. Per-file errors are collected while other files continue. Status-bar progress and cancellation retain completed exports and caches; closing cancels remaining work. The last output folder is saved as `export/folder`.

## Search pipeline

1. `discover_documents` enumerates the file types selected by `SearchOptions.search_scope` in stable relative-path order. Recursion is controlled by `SearchOptions.recursive`. `SearchOptions.stem_glob` optionally filters the complete `Path.stem` (only the final extension is removed) with case-folded `fnmatchcase` glob matching. Empty means no filter. This filter also applies to explicitly supplied `paths` before reading or conversion, so progress and scanned counts include only eligible files. It is independent of content regex/case settings and never matches parent directories.
2. Word files are screened before candidates enter a PDF conversion queue. `word_may_match` streams WordprocessingML text from DOCX, checks literal patterns across runs, and returns on the first possible hit without creating page numbers or official matches. Screening ignores case and relaxes whitespace and hyphens. Screening requires a normalized contiguous phrase rather than scattered characters. It reads body, header/footer, note, chart, and diagram content, excluding style definitions. Patterns containing regex operators, legacy `.doc`, dynamic fields, embedded objects, or parse failures bypass screening; enabling regex for a literal phrase does not bypass it. Ordinary images, numbering, and unused styles do not force conversion; drawing text is extracted too. Valid PDF caches take precedence. Conversion prefers Microsoft Word on Windows, with LibreOffice as fallback; all application tabs share one lazily started Word instance, with COM initialization, export, and cleanup on the conversion thread. Macros and link updates are disabled and sources are read-only. Cache keys include converter, source path, size, and modification time. Startup removes entries unused for 30 days and evicts by LRU down to 500 MB; manual clearing is disabled during search or batch PDF export.
3. Each PDF is opened independently. For a protected document, `unlock_pdf` obtains a credential through the optional `password_requested(path, incorrect)` callback and validates it with `Document.authenticate()`. Wrong passwords can be retried; skipping produces a per-file warning. Only successful authentication invokes `password_accepted`, followed by normal extraction and matching. Corrupt, empty, textless, or unconvertible files remain non-fatal warnings.
4. Each page is extracted with PyMuPDF `rawdict`. `TEXT_PRESERVE_IMAGES` is explicitly disabled so image payloads are never decoded during text search.
5. Text blocks, lines, spans, and characters are traversed in reading order. Every visible character retains its page index and exact bounding box.
6. Whitespace within a line is collapsed; physical line and page boundaries become `\n` with non-geometric character references. Default extraction preserves line-ending hyphens. Optional `SearchOptions.ignore_line_wraps` is off by default. When enabled, `layout_text.py` uses RAWDICT block IDs and direction, vertical spacing, horizontal overlap, and detected cells to identify adjacent wraps on the same page. CJK boundaries omit synthetic spaces; Latin words retain one space and ASCII letter-to-letter wrap hyphens are removed only for recognized wraps. Real within-line and edge spaces remain. Separate blocks, columns and cells use hard separators; page boundaries remain newlines. Joined lines form one logical line for anchors. Table analysis runs only on pages with vector paths; failed detection disables joining on that page. This conservative heuristic cannot reliably identify every borderless table or merged paragraph.
7. The complete normalized document is searched. Plain text is escaped before compilation; regular expressions use Unicode `VERSION1 | MULTILINE`, optional full case folding, and a per-document timeout. `^`/`$` match preserved line boundaries by default; `\A`/`\Z` anchor the complete document, and `(?-m)` disables multiline anchors. Dot remains non-DOTALL unless `(?s)` is requested; `\s+` or explicit `\n` can match across lines/pages. Literal spaces no longer span breaks. PDF subprocesses and preliminary DOCX matching share these compiler flags. Regression tests cover both anchors, page boundaries, whole-word wrapping, mode overrides, layout joins, DOCX paragraphs, original highlight coordinates and subprocess behavior.
8. Zero-width matches are ignored. Each non-empty match is mapped back to the bounding boxes of only the characters it covers.
9. Match summaries stop at the nearest CJK/ASCII punctuation (`，。！？；：、,.!?;:`) or paragraph/cell newline boundary. Context radius limits always apply, even when distant punctuation exists. Whitespace is collapsed to one line and summaries are capped at 160 characters, abbreviating long matched spans when necessary. Full `matched_text`, match coordinates, and PDF highlights remain intact.

`SearchOptions.whole_word` defaults to false. `compile_pattern` wraps the escaped literal or regex in `(?<!\w)(?:…)(?!\w)` so alternatives retain their scope, capture/backreference numbers are unchanged, and punctuation-ending terms such as C++ remain searchable. A verbose-mode trailing comment is terminated before closing the wrapper. Unicode word characters define boundaries, including Chinese characters and combining marks, without dictionary segmentation. PDF subprocesses and preliminary DOCX extraction share this compiler; conservative Word screening may still enqueue candidates for PDF confirmation. The per-tab `whole_word_button` sits between case and regex, uses a 1 px |ab| glyph, and is locked during that tab's search/export. Old sessions default off; new tabs inherit the current setting.

The normalized text string and `CharacterRef` tuple always have identical lengths. Synthetic separators have a page reference but no rectangle, so expressions can cross pages without producing artificial highlights.

## Incremental results and concurrency

Each `FolderTab` owns a small QThreadPool, so waiting export/search coordination in one tab cannot exhaust the GUI-wide pool and starve another tab. Each search reuses its own spawn PDF subprocess. The application owns one `WordConversionService` and one dedicated renderer thread; COM initialization, lazy Word reuse, conversion and shutdown stay on that thread. Requests are FIFO and keyed by resolved source path, size and modification time. Tickets share a Future; releasing one subscriber does not cancel another. Unused queued requests are skipped, and source changes invalidate results. Valid caches bypass busy conversions. Search discovery submits candidates asynchronously and keeps processing other files; Future callbacks put completed PDFs on an unbounded ready queue without waiting for PDF search. Existing PDFs and caches can report first.

`PreliminaryDocument` and `PreliminaryMatch` contain DOCX passages and offsets, never page numbers or PDF rectangles. `word_text.py` joins XML runs within paragraphs, keeps paragraph boundaries, applies search case/regex options with a timeout, and bounds context. Unsupported extraction does not reject candidates. A per-file resolved event replaces preliminary rows with authoritative PDF results; false positives disappear and failures retain a non-animated error preview. `TextMatch` remains exclusively PDF-derived. Preview states distinguish queued conversion (with documents ahead), converting, and PDF verification. Pending previews disable page controls and clipboard tools. A QTimer-driven indicator stops when hidden; selection/request ownership prevents late results from changing another page.

Folder selection and filter changes affect the next search without preconverting the folder. Cancellation or window closure stops screening and queued conversions, terminates the PDF search subprocess, and cleans up the conversion thread and COM after an active Word call returns. Per-file failures remain warnings and do not block subsequent documents.

Encrypted PDF authentication uses a Pipe exchange: the child requests a password with retry state, the parent supplies input, and the child acknowledges successful authentication before streaming matches. `SearchWorker` emits a `PdfPasswordRequest`; the UI responds through a nonblocking, masked `QInputDialog`. Waiting checks cancellation every 50 ms; cancellation/closure rejects the prompt and terminates the child without manipulating widgets from worker threads. The window owns `PdfPasswords`, keyed by absolute path, size, and modification time, for repeated searches and authentication of each independent preview render. Preview workers release their temporary password reference when done. Credentials never enter `SearchOptions`, result models, QSettings, warnings, or disk caches; no decrypted copy is produced. Window closure clears credentials and rejects late authentication results.

Preview rendering is separate from search work. Each selection creates a `PreviewRenderWorker` that opens its own document handle, renders one page to a `QImage`, and paints translucent highlight rectangles off the UI thread. A monotonically increasing request ID ensures results from older selections or resize requests are discarded. Only conversion to `QPixmap` and widget updates occur on the UI thread.

The render worker extracts current-page `rawdict` text (images disabled) from the same authenticated document handle and builds immutable `PageText`/`PageGlyph`/`PageLine` data. Text preserves line/block breaks; glyph rectangles and search highlights are transformed with `page.rotation_matrix`. `SelectablePageLabel` maps mouse positions through the pixmap origin and zoom, finds the nearest line and glyph, and uses text direction to determine endpoints. One Select and copy text toolbar button uses a text-lines-and-caret glyph. Dragging paints only a translucent overlay; mouse release automatically copies the final selection. Page select-all also copies automatically without modifying the PDF. Reverse selection, Esc, Ctrl+C/⌘C, and context menus are supported. Page/file changes and re-rendering clear selection and invalidate old text layers; stale request IDs cannot restore them. Temporary Windows clipboard contention uses bounded timer retries; closing or clearing the document cancels pending copies.

The preview toolbar separates navigation, copy tools, and zoom controls. Page-image copying encodes the complete rendered pixmap to PNG in memory with `QBuffer`, supplying both `image/png` and native image data through `QMimeData`. It retains search highlights at the current preview resolution but excludes the painted selection overlay. A render-readiness flag prevents stale-page copies during navigation or rendering, independent of text availability. Windows clipboard ownership is checked with bounded timer retries; clearing the document cancels pending image copies.

Cancellation uses a thread-safe event checked while waiting for IPC or document preparation, terminating the PDF search subprocess when necessary. Regex execution has its own timeout to contain catastrophic backtracking. Closing the window invalidates pending preview requests and requests search cancellation.

The default `README.md` is Traditional Chinese, so GitHub and the package readme open in Traditional Chinese. English is maintained in `README.en.md`. Both README files are included in source distributions.

## UI and persisted settings

Each FolderTab hosts a labeled Search options row inside Search target, containing the six existing 34 px option buttons with 4 px spacing. The main toolbar retains appearance, cache, export and integration tools. Existing per-tab persistence and search-time disabling are unchanged. File and match groups share a vertical QSplitter (files above matches), while preview stays to the right. Restoring legacy splitter state explicitly resets its orientation to vertical because Qt serializes orientation along with sizes; the existing saved ratios remain usable.

File manager integration is opt-in through the checkable context_menu_button immediately left of Language, with install/remove CLI equivalents. MainWindow synchronizes every tab from actual OS registration on startup, tab switches and operations, reverting failed toggles; tooltips describe install/remove and unsupported platforms are disabled. The button shares the 34 px footprint, 32 px state background and 1 px folder/menu artwork. `app.parse_arguments` accepts multiple positional paths after `--`; `open_startup_paths` resolves them, maps files to parents, and opens folder tabs after restoring the session. The stdlib-only bootstrap forwards paths to the current user's primary instance before importing the GUI or PDF engine; no automatic search runs. With no arguments it activates that window; --new-window bypasses forwarding. Frozen launches use sys.executable; Python installs use the current interpreter with `-m rgpdf` and pythonw.exe when available on Windows, independent of PATH and working directory.

Windows registers per-user `Directory\shell\rgPDF`, `Directory\Background\shell\rgPDF` and `SystemFileAssociations\.pdf|.doc|.docx\shell\rgPDF` under `HKCU\Software\Classes`, without modifying default file associations, with `%1` / `%V`, Document selection for folder items, no MultiSelectModel on the background verb, and a quoted command ending in `-- "<placeholder>\."`. The final dot avoids trailing-backslash quote ambiguity for drive/UNC roots. File commands use the exact quoted `%1` path without the folder-only `\.` suffix. Registration checks cover all five verbs and repair partial/older registrations. Removal deletes only these keys and their command children; SHChangeNotify refreshes association state. See [Microsoft shortcut-menu documentation](https://learn.microsoft.com/en-us/windows/win32/shell/context).

macOS writes only the rgPDF-owned `~/Library/Services/Open in rgPDF.workflow` bundle: Contents/Info.plist advertises a Finder-only service accepting public.folder, com.adobe.pdf, com.microsoft.word.doc and org.openxmlformats.wordprocessingml.document; document.wflow runs the built-in Automator shell action with inputMethod=1 and safely quoted `"$@"`. Packaged apps launch through `open -n -a <absolute app> --args`; source/Python installs use the interpreter command. The shell launches asynchronously, then returns. `pbs -update` refreshes service discovery. Removal verifies the bundle identifier, rejects symlinks/unrelated files and removes only owned files/empty directories. No app bundle signatures or global preferences are edited. Moving the application requires re-registration. See [Apple Quick Action guidance](https://support.apple.com/guide/automator/aut73234890a/mac). Tests use isolated registry keys/temp workflows and cover Windows argv parsing, toolbar placement/state, CLI startup, idempotence and ownership checks; a macOS-only test invokes `/usr/bin/automator` to verify folder and PDF input delivery without opening the real app.

`PdfPreview.trim_box_button` is a per-preview, default-off toggle kept across page/match changes, without persistence. `PreviewRenderWorker` intersects page.trimbox with page.cropbox and applies a valid, nonempty result via set_cropbox only to its private unsaved document. Missing/unusable boxes fall back to the visible page. Fit dimensions, rasterization and extract_page_text use that cropped page; search highlight rectangles shift by old CropBox origin minus new origin before applying the new rotation matrix. This keeps rotated text selection and highlights aligned, including nonzero CropBox origins. Clipboard PNG uses the resulting cropped raster; text copy includes only retained glyphs. Search and PDF exports retain full document content. Regression tests cover all four rotations, offset CropBoxes, fit scaling, text/PNG copying, highlights, missing TrimBox fallback and unchanged source bytes. Coordinate behavior follows the [PyMuPDF Page documentation](https://pymupdf.readthedocs.io/en/latest/page.html).

Main and preview toolbar buttons keep their 34×34 px hit areas and centered glyphs. A 1 px QSS margin on each edge reduces hover, pressed, and checked backgrounds to 32×32 px while retaining the 8 px corner radius and existing control spacing.

The tab/pane divider and inactive tab underlines use Midlight; the outer workspace frame retains Mid. Each FolderTab listens to QApplication.focusChanged and updates a focusWithin property on its search, file, match, and preview groups; QSS emphasizes only the focused pane's border. PdfPreview redirects focus to its page label, including clicks in the scroll viewport, and handles unmodified Left/Right and PageUp/PageDown before QScrollArea consumes them. Existing text copy/select shortcuts remain available. Both currentItemChanged and itemClicked select a match; show_match skips redundant renders for the same path/match/page, but returns to start_page and renders when the preview has moved, preserving zoom mode. Regression coverage exercises focus transitions, both paging key pairs, page boundaries, and re-clicking the selected match.

The main window hosts the settings toolbar and folder tabs. Each folder tab uses a horizontal splitter:

- Left: a Search target group containing folder, filename-stem filter, and pattern controls above file and match result tables. A three-state toolbar button selects PDF, Word, or combined discovery.
- Right: full-height PDF preview with previous/next navigation through every document page, fit-to-width, fit-to-page, and zoom.

The official display name is rgPDF. The command, Python package, cache paths, and settings identifiers remain `rgpdf`. Selecting a match opens its start page; preview arrows browse adjacent pages, including pages without matches, and are disabled at document boundaries. Highlights remain tied to the selected match. Fit-to-page uses the smaller of the available viewport width/page width and height/page height ratios, without the manual zoom minimum, so even large pages fit completely. Both fit modes recompute on pane resize and page navigation; manual zoom exits either fit mode.

Result tables disable the header’s default last-section stretching so per-column resize modes apply: file counts size to contents and filenames use the remaining width.

`MainWindow` hosts a QTabWidget; `FolderTab` owns its form, splitters, result models and preview. The host installs the active tab's toolbar and status widgets, preserving each tab's option state. Folder identities use resolved paths and Windows normcase, duplicate names use distinguishing parent suffixes, and drops open every valid local folder/file-parent even while other tabs work. A single empty tab remains after the last folder closes. FolderTabState is stored in a QSettings array, including search conditions, splitter states and export destination; order and active index are restored without results, credentials or automatic searches. Legacy settings seed the first session and remain last-used defaults. Missing paths remain visible with search/export disabled. Global appearance and session-only PDF passwords are shared. FolderTabBar reserves a compact 32 px tab row in its size hints; the corner add button uses a 28×28 px footprint so it remains fully visible.

A shared `folderWorkspaceFrame` QFrame encloses the complete QTabWidget, including its tab bar, with a 1 px Mid border and 4 px corners. Its layout has zero margins/spacing; the central layout retains 12 px side and 8 px bottom margins, with no top gap below the toolbar. The toolbar uses the Window background and has no bottom border. QTabWidget document mode remains disabled so its pane can draw only a 1 px Midlight top divider, shifted up 1 px to meet the tab underlines; the pane has no separate side/bottom frame. Tabs have zero top margin, a 20 px minimum content height, and 5 px top padding, producing a 32 px row. Selected tabs use Base with a 2 px Highlight underline; inactive tabs are transparent with AlternateBase on hover and a 1 px Midlight bottom border so their background cannot obscure the pane edge. Bottom padding is 6 px for inactive tabs and 5 px for the selected 2 px underline, preserving equal tab heights. Custom 20×20 px close buttons draw a 1 px, 6×6 px cross and dispatch through the folder widget identity, so reordering cannot change their target. Labels use middle elision and full-path tooltips. The toolbar shares the frame’s 12 px side margins, aligning both left and right edges.

Settings use `QSettings("rgpdf", "rgpdf")`:

| Key | Meaning |
| --- | --- |
| `appearance/language` | `system`, `zh_TW`, or `en` |
| `appearance/theme` | `system`, `light`, or `dark` |
| `appearance/highlight_color` | Highlight color as `#rrggbb` |
| `session/tabs` | Ordered per-folder settings array, including search conditions, splitter states and export destination |
| `session/current_tab` | Active restored folder index |
| `search/folder` | Last selected folder |
| `export/folder` | Last Word PDF export destination |
| `search/stem_glob` | Filename-stem glob filter; empty means no filter |
| `search/pattern` | Last search pattern |
| `search/use_regex` | Regular-expression mode |
| `search/ignore_line_wraps` | Layout-aware joining of physical line wraps; off by default |
| `search/case_sensitive` | Case-sensitive matching |
| `search/whole_word` | Whole-word matching for literal/regex; off by default, independently persisted per tab |
| `search/recursive` | Include subfolders |
| `search/scope` | `pdf`, `word`, or `all` |
| `window/geometry` | Window geometry |
| `window/main_splitter` | Left/preview split |
| `window/result_splitter` | File/match split |

The filename-stem and search-pattern help icons align vertically immediately to the left of their input fields and share a rich-text help popup implementation with localized syntax explanations and examples. PDF indicators render the bundled Adobe Acrobat SVG through `QSvgRenderer`, at the same 16×16 px size as Word in single-format mode; both marks use 14×14 px and partially overlap in combined mode (PDF upper-left, Word lower-right). Both platform bundles include the SVG; its source is recorded in the third-party notices. Icon outlines use the shared `SettingsButton.STROKE_WIDTH` of 1 logical px; brand marks retain their original vector artwork. Action buttons share a 34×34 px footprint, 4 px padding, and 4 px control spacing across panes; circular color swatches retain their 28×28 px size. `SettingsToolBar` reapplies shared spacing and symmetric 4 px margins after Qt polish, show, and style-change events. The toolbar remains 42 px high (34 px buttons plus 4 px above and below), including after theme changes. Toolbar glyphs use small vertical offsets for asymmetric artwork so their visible centers align with language and theme icons. Language and theme buttons cycle through their three modes. Checked toggle buttons retain the hover `palette(midlight)` background without an outline; backgrounds share the 8 px `SettingsButton.CORNER_RADIUS`. The dark theme uses a Unit-01-inspired deep-purple palette, neon-green checked icons and selection backgrounds with dark selection text, and orange focus/link accents. Light-mode toggles keep neutral checked styling. The highlight button displays the selected color as a centered 16×16 px swatch; Browse and recursive-folder icons use unfilled theme-colored outlines; the folders share a 14×10 px outline offset by 6×6 px, with clipping hiding the rear outline beneath the front folder. Its color palette offers presets and a native `QColorDialog`.

Help rings use a 16×16 logical-pixel outer boundary snapped through QPainter.deviceTransform to device-pixel edges. An odd-even filled ring retains the shared 1 logical px thickness and antialiasing, avoiding the soft cardinal edges of an integer-centered ellipse stroke; this also respects high-DPI redirected icon exports.

README icons are exported by `uv run python scripts/generate_toolbar_icons.py`: light images stay in `docs/toolbar/`, and dark images are in `docs/toolbar/dark/`. Both variants render the shared button painter with the theme’s higher-contrast text color and an opaque base-color tile at 2× resolution (68×68 px, displayed at 34×34 px). README `<picture>` elements use `prefers-color-scheme: dark` to select dark assets and keep a readable light fallback for viewers that ignore source selection.

`SearchProgressBar` retains the existing track and chunk styling and paints its percentage twice: `Text` over the track and `HighlightedText` clipped to the filled area. Dark mode therefore uses dark text over neon green and light text over the unfilled track; right-to-left and inverted progress are also supported.

## Testing and packaging

The Windows spec uses PyInstaller `COLLECT` (onedir): a versioned ZIP contains `rgpdf.exe` and its adjacent `_internal` dependencies. It does not extract an embedded runtime on startup or populate a persistent runtime cache. The macOS App bundle remains a directory bundle. A custom runtime hook defers PyInstaller's QtCore resource registration until GUI ownership is established; its normal plugin environment setup remains intact.

`bootstrap.py` calls `freeze_support` first so frozen PDF workers bypass GUI IPC, then handles CLI arguments using `cli.py`. `instance.py` starts a bounded JSON queue before importing `app.py`, loading settings, or cleaning Word caches. Windows uses a named pipe; POSIX uses a user-owned mode-0600 Unix socket and a locked file in the temporary directory to serialize startup and recover stale sockets. No pickle is accepted. Concurrent first launches select one owner; secondary launches use bounded connection/retry timeouts and exit after queue acceptance. Queue acceptance can precede actual GUI processing. Closing stops acceptance. A Qt timer drains requests on the GUI thread, reuses folder tabs and restores/activates the window; Windows senders grant foreground permission. Path resolution and filesystem checks happen after forwarding, not in the lightweight sender. `--new-window` creates an independent window outside this primary-instance endpoint.

IPC tests cover queued startup requests without a GUI loop, Unicode/spaced paths, concurrent ownership, endpoint reuse, malformed requests, shutdown rejection, import isolation and existing-tab/minimized-window behavior. The remote Windows smoke test extracts the actual ZIP, opens the GUI, forwards a file to its parent folder, checks for one GUI process and verifies that the forwarding trace contains no GUI/PDF imports. `RGPDF_STARTUP_TRACE` enables an explicit JSON-lines diagnostic file; no trace file is created by default. Native timings include process launch and window readiness, while forwarding completion only confirms acceptance. These checks do not establish the cause of earlier intermittent five-minute startup delays.

Tests cover literal and regex matching, case behavior, cross-page mapping, dehyphenation, context, corrupt/textless PDFs, streamed results, settings, themes, and preview rendering. They also verify DOCX screening, unsupported-content fallback, cached-PDF bypass, separation of candidates and official results, screening during conversion, ready-PDF bypass, process reuse, and cancellation cleanup. Password tests also cover AES-encrypted PDFs with user/owner credentials, retry, per-file skip, empty opening passwords, preview navigation, session credential cleanup, and cancellation/closure while awaiting input.

Tests also cover rotated and encrypted page text selection, automatic clipboard copying and retries, full-page PNG MIME data, system-menu dispatch/localization, Word export cache reuse and creation, output collisions, skip/overwrite, cancellation, file filtering, stale scan rejection, and the main-window export flow.

Additional tests cover FIFO/deduplicated conversion, independent subscriber cancellation, cache bypass during blocked rendering, stale source rejection, simultaneous searches/exports across tabs, early results and ready PDFs bypassing blocked Word conversion, confirmation/no-hit/failure transitions, close confirmation and isolation, session migration/restoration, and preview state persistence.

Whole-word tests cover prefixes/suffixes, underscores/digits, CJK and combining marks, punctuation-ending literals, regex alternatives and backreferences, verbose comments, case sensitivity, PDF geometry, preliminary DOCX results, subprocess propagation, and independent tab restoration.

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
