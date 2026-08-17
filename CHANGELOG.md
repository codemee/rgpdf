# Changelog

[繁體中文](CHANGELOG.zh-TW.md) · English

All notable changes are documented here. Immutable releases use `vX.Y.Z`; the moving `latest` tag points to the newest published release.

## 0.0.6 — 2026-08-17

- Changed the macOS GitHub Release download from ZIP to a DMG with an Applications shortcut.

## 0.0.5 — 2026-08-17

- Added a self-contained macOS arm64 App bundle, Retina `.icns` icon, and one-command build script.
- Added macOS App launch, bundle metadata, architecture, and ad-hoc signature verification.
- Changed releases to trigger from `vX.Y.Z` tags, testing and building Windows x86-64 and macOS arm64 in parallel.
- Automated a single GitHub Release with versioned downloads, SHA-256 files, and subsequent PyPI publication.
- Added SHA-256-verified corresponding source archives for PyMuPDF, MuPDF, PySide6, Shiboken6, and Qt.

## 0.0.4 — 2026-08-17

- Licensed rgpdf under GNU AGPLv3 and added complete third-party notices and release compliance guidance.
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
