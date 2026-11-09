# Project workflow

- Use uv for Python dependency management, tests, and running the application.
- During development, run relevant tests with `uv run python scripts/check.py tests/test_example.py`.
  After the implementation settles, run `uv run python scripts/check.py` once for the full suite.
  Reuse its matching full-pass record for version/documentation-only changes; use `--force`
  to diagnose suspected flaky tests. Do not repeat unchanged full runs or build trial
  artifacts for routine UI edits. Packaging changes may require a remote trial build.
  Release CI always runs the full suite independently on Windows and macOS.
- After changes and checks, launch `uv run rgpdf` for the user's manual testing.
- Do not build executable or App artifacts locally. Push a version tag and let
  `.github/workflows/publish-pypi.yml` build and publish Windows and macOS artifacts.
- Keep English and Traditional Chinese README, technical documentation, and
  changelogs synchronized. Export README toolbar icons using
  `uv run python scripts/generate_toolbar_icons.py` after changing their appearance.
