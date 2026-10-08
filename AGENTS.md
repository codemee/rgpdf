# Project workflow

- Use uv for Python dependency management, tests, and running the application.
- After changes and checks, launch `uv run rgpdf` for the user's manual testing.
- Do not build executable or App artifacts locally. Push a version tag and let
  `.github/workflows/publish-pypi.yml` build and publish Windows and macOS artifacts.
- Keep English and Traditional Chinese README, technical documentation, and
  changelogs synchronized. Export README toolbar icons using
  `uv run python scripts/generate_toolbar_icons.py` after changing their appearance.
