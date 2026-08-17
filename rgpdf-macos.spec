# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from pathlib import Path

project_root = Path(SPEC).resolve().parent
version_namespace = {}
exec((project_root / "src" / "rgpdf" / "__init__.py").read_text(encoding="utf-8"), version_namespace)
version = version_namespace["__version__"]

a = Analysis(
    [str(project_root / "src" / "rgpdf" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[
        (str(project_root / "src" / "rgpdf" / "assets" / "rgpdf.svg"), "rgpdf/assets"),
        (str(project_root / "LICENSE"), "licenses"),
        (str(project_root / "THIRD-PARTY-NOTICES.md"), "licenses"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="rgpdf",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
bundle_files = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="rgpdf")
app = BUNDLE(
    bundle_files,
    name="rgpdf.app",
    icon=str(project_root / "build-assets" / "rgpdf.icns"),
    bundle_identifier="io.github.codemee.rgpdf",
    version=version,
    info_plist={
        "CFBundleDisplayName": "rgpdf",
        "CFBundleName": "rgpdf",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
)
