# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)


project_root = Path(SPEC).resolve().parent
version_namespace = {}
exec(
    (project_root / "src" / "rgpdf" / "__init__.py").read_text(encoding="utf-8"),
    version_namespace,
)
version = version_namespace["__version__"]
version_parts = tuple(int(part) for part in version.split("."))
file_version = (*version_parts, 0)[:4]

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=file_version,
        prodvers=file_version,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "meebox"),
                        StringStruct("FileDescription", "rgpdf — PDF Search"),
                        StringStruct("FileVersion", version),
                        StringStruct("InternalName", "rgpdf"),
                        StringStruct("LegalCopyright", "Copyright (C) 2026 meebox"),
                        StringStruct("OriginalFilename", "rgpdf.exe"),
                        StringStruct("ProductName", "rgpdf"),
                        StringStruct("ProductVersion", version),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

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
    a.binaries,
    a.datas,
    [],
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
    icon=str(project_root / "build-assets" / "rgpdf.ico"),
    version=version_info,
)
