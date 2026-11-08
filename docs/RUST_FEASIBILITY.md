# Rust feasibility assessment

[繁體中文](RUST_FEASIBILITY.zh-TW.md) · English

Reviewed 2026-11-08 against rgPDF 0.1.10. This is research and a proposed migration path, not a Rust implementation or a measured performance claim.

Full migration is technically feasible, but entails a GUI and integration rewrite, not a mechanical Python translation. The central acceptance criteria are Windows single-EXE deployment, macOS support, equivalent text/bounding-box behavior, regex compatibility, and independent searches with serialized Word conversion.

| Area | Candidate | Main work/risk |
| --- | --- | --- |
| Desktop UI | egui/eframe or Slint | Rebuild tabs, tables, splitters, tooltips, focus, clipboard, text selection, IME and custom artwork; verify Windows/macOS behavior. CXX-Qt is another integration route but retains Qt deployment concerns. |
| PDF | mupdf-rs first; pdfium-render alternative | MuPDF retains the current engine family and exposes rendering, authentication and positioned/structured text. Preserve reading order, glyph mapping, crop/rotation transforms, TrimBox and table-aware joining. PDFium changes the engine and requires fresh compatibility baselines. |
| Regex | regex plus an explicitly chosen advanced engine, or PCRE2/fancy-regex | Rust regex excludes look-around/backreferences used by current matching. No candidate is automatically identical to Python regex FULLCASE/VERSION1. Preserve default multiline, whole-word boundaries and bounded execution. |
| Word | windows-rs COM on Windows; LibreOffice process elsewhere | Port STA lifetime, read-only opening, macro suppression, cancellation and one-at-a-time conversion. Rust does not remove the external conversion requirement or guarantee faster Word export. |
| Jobs/settings/OS | Rust workers/channels and platform APIs | Preserve per-tab state, queued conversion sharing, cancellation, encrypted-PDF prompts, Explorer/Finder integration and settings migration. |

Single-EXE output depends on the whole dependency graph. Switching to Rust alone does not remove a dynamically loaded PDF/GUI DLL. pdfium-render supports static linking but does not build or supply the static PDFium library. Static MuPDF/PDFium, appropriate Windows CRT linkage, embedded resources and clean-machine tests must be proved before committing to the architecture. Binary size and startup time require measurement; external OS scanning may still delay an EXE.

Rust regex match positions are UTF-8 byte offsets; Python's current character references use string-character indices. The port needs an explicit mapping from regex offsets to glyph/page geometry, including Chinese characters and combining marks. Merely copying slice indices will misplace highlights. Advanced regex limits are not interchangeable with Python's wall-clock timeout; preserve a cancellable worker boundary if strict deadlines are required.

Recommended proof sequence:

1. Build one Windows EXE and a macOS App that open the user's real PDFs, extract positioned text and render pages without Python. Confirm Chinese fonts and password authentication.
2. Reproduce the 33 anchored / 34 unanchored matches in F6791_CH06(30).pdf; compare match text, page numbers and rectangles with saved Python baselines. Include dehyphenation, table boundaries, full words, captures and Unicode cases.
3. Implement a small viewer with zoom, TrimBox, mouse text selection/copy and PNG clipboard output, then evaluate Slint/egui ergonomics and Chinese IME.
4. Add one Word conversion queue and concurrent searches. Only then port the full UI/session/OS integrations and migrate the existing regression suite.

For the immediate startup problem, a Rust-only cache launcher is a much smaller experiment: it can retain the Python application and validated behavior while replacing the external bootstrap. The current cache branch instead uses a Windows .NET Framework prototype to validate caching independently of a language rewrite. A full Rust app is more appropriate when removing Python/Qt and changing long-term packaging are goals in their own right. These are distinct scopes, and neither has yet been benchmarked here as a Rust program.

Primary sources: [mupdf-rs](https://github.com/messense/mupdf-rs), [pdfium-render static linking](https://github.com/ajrcarey/pdfium-render#static-linking), [egui](https://github.com/emilk/egui), [Slint](https://github.com/slint-ui/slint), [CXX-Qt](https://github.com/KDAB/cxx-qt), [Rust regex](https://github.com/rust-lang/regex), [byte offsets](https://docs.rs/regex/latest/regex/struct.Match.html), [fancy-regex](https://github.com/fancy-regex/fancy-regex), [PCRE2 Rust bindings](https://github.com/BurntSushi/rust-pcre2), [windows-rs](https://github.com/microsoft/windows-rs).
