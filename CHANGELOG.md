# Changelog

[繁體中文](CHANGELOG.zh-TW.md) · English

All notable changes are documented here. Immutable releases use `vX.Y.Z`; the moving `latest` tag points to the newest published release.

## Unreleased

- Added light/dark README icon images with automatic color-scheme selection and opaque fallback tiles for Markdown viewers without picture support.

## 0.0.11 — 2026-10-16

- Reshaped the application icon into an equal-width/height silhouette with balanced margins, preserving the blue folded-document and `.*` mark.

## 0.0.10 — 2026-10-16

- Kept the toolbar height at 42 px with symmetric 4 px margins across startup and theme changes.
- Changed action icon outlines to a shared 1 px stroke and regenerated the README icons.
- Fixed Qt resetting toolbar button spacing to zero when showing the window or changing themes; actual spacing within each button group now remains 4 px.

## 0.0.9 — 2026-10-16

- Standardized action-control spacing at 4 px across the search, help, preview, toolbar, and color panels; retained compact circular color swatches.
- Aligned asymmetric toolbar glyphs by their visible vertical centers so language and theme controls line up visually with neighboring icons.
- Fixed clipped file match counts in narrow result panes by honoring content-sized numeric columns instead of forcing the final column to stretch.
- Aligned both help icons immediately to the left of their input fields. Added a help icon for the filename-stem filter, opening localized Glob syntax and examples in the same popup style as Search pattern help.
- Added a persisted filename-stem glob filter below Document folder, supporting `*`, `?`, and character classes before PDF reading or Word conversion; empty means no filter.
- Changed all application action buttons to shared vector icons, moving their labels to localized tooltips and accessible names; exported the additional icons for the README guide.
- Added a Fit page preview button that fits the whole page within the pane and adapts to resizing and page navigation, alongside Fit width.
- Changed preview arrows to browse every document page, including pages without matches, with boundary-aware button states. Use the match pane to jump between matches.
- Named the application rgPDF throughout the UI, documentation, and release display metadata; the command and Python package remain `rgpdf`.

## 0.0.8 — 2026-10-09

- Added a persisted three-state toolbar button for PDF-only, Word-only, or combined search, with distinct PDF and Word marks.
- Reordered toolbar groups so language and color theme sit immediately before About, and replaced the recursive-search glyph with nested folders.
- Added `.doc` and `.docx` search through cached PDF conversion, preferring Microsoft Word on Windows and falling back to LibreOffice.
- Word results now reuse the existing page preview, regular-expression matching, and precise highlighting pipeline without modifying source documents or running macros.
- Added startup cache expiration after 30 unused days, a 500 MB least-recently-used cap, and a toolbar action for clearing Word conversion cache.
- Added a README toolbar guide using icons exported from the application; executable builds now run only in the remote release workflow.

## 0.0.7 — 2026-08-17

- Added macOS Apple Silicon DMG download, SHA-256 verification, drag-to-install, and first-launch instructions to the installation section.

## 0.0.6 — 2026-08-17

- Changed the macOS GitHub Release download from ZIP to a DMG with an Applications shortcut.

## 0.0.5 — 2026-08-17

- Added a self-contained macOS arm64 App bundle, Retina `.icns` icon, and one-command build script.
- Added macOS App launch, bundle metadata, architecture, and ad-hoc signature verification.
- Changed releases to trigger from `vX.Y.Z` tags, testing and building Windows x86-64 and macOS arm64 in parallel.
- Automated a single GitHub Release with versioned downloads, SHA-256 files, and subsequent PyPI publication.
- Added SHA-256-verified corresponding source archives for PyMuPDF, MuPDF, PySide6, Shiboken6, and Qt.

## 0.0.4 — 2026-08-17

- Licensed rgPDF under GNU AGPLv3 and added complete third-party notices and release compliance guidance.
- Added an in-app About dialog with exact-version source and license links.
- Added reproducible PyInstaller packaging for a self-contained Windows x86-64 executable.
- Added a generated multi-resolution Windows icon, executable version metadata, and packaged-resource checks.
- Added a GitHub Actions Windows build and GUI startup smoke test.
- Added unsigned, versioned GitHub Release downloads with SHA-256 verification files.

## 0.0.3 — 2026-08-15

- Standardized toolbar icons at 20×20 px inside 34×34 px buttons with 4 px padding.
- Removed toolbar button borders, including from enabled states.
- Set consistent 4 px spacing between toolbar buttons across platforms.

## 0.0.2 — 2026-08-15

- Vertically aligned search-form labels with their input controls.
- Added interactive, localized search-pattern help with examples and a clickable regular-expression reference.
- Added the package version to the application window title.
- Added secure automated PyPI publishing through GitHub Trusted Publishing.

## 0.0.1 — 2026-08-15

- Initial public release.
- Added cross-platform multi-PDF plain-text and regular-expression search.
- Added incremental per-match results and non-blocking PDF previews.
- Added precise per-character highlights with configurable colors.
- Added English/Traditional Chinese localization and system/light/dark themes.
- Added persistent search, appearance, and window-layout settings.
