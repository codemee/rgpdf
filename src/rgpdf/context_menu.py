# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

"""Opt-in, per-user Explorer verbs and Finder Quick Action registration."""

from __future__ import annotations

import ctypes
from pathlib import Path
import plistlib
import shlex
import subprocess
import sys
from uuid import uuid4


WINDOWS_KEYS = (
    (r"Software\Classes\Directory\shell\rgPDF", "%1"),
    (r"Software\Classes\Directory\Background\shell\rgPDF", "%V"),
)
WINDOWS_FILE_KEYS = tuple(
    (rf"Software\Classes\SystemFileAssociations\{extension}\shell\rgPDF", "%1")
    for extension in (".pdf", ".doc", ".docx")
)
SERVICE_ID = "io.github.codemee.rgpdf.finder-service"
SERVICE_TYPES = ("public.folder", "com.adobe.pdf", "com.microsoft.word.doc",
                 "org.openxmlformats.wordprocessingml.document")


def launch_command() -> list[str]:
    executable = Path(sys.executable).absolute()
    if getattr(sys, "frozen", False):
        return [str(executable)]
    if sys.platform == "win32" and executable.with_name("pythonw.exe").is_file():
        executable = executable.with_name("pythonw.exe")
    return [str(executable), "-m", "rgpdf"]


def windows_command(placeholder: str, *, is_file: bool = False) -> str:
    # Appending \. also quotes drive/UNC roots safely: a trailing backslash
    # immediately before a closing quote has special meaning to Windows argv.
    suffix = "" if is_file else "\\."
    return subprocess.list2cmdline(launch_command()) + f' -- "{placeholder}{suffix}"'


def service_path() -> Path:
    return Path.home() / "Library" / "Services" / "Open in rgPDF.workflow"


def finder_workflow() -> tuple[dict, dict]:
    command = launch_command()
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).absolute()
        bundle = next((p for p in executable.parents if p.suffix == ".app"), None)
        if bundle is not None:
            command = ["/usr/bin/open", "-n", "-a", str(bundle), "--args"]
    script = shlex.join(command) + ' -- "$@" >/dev/null 2>&1 &'
    action = {
        "AMAccepts": {"Container": "List", "Optional": False,
                      "Types": ["com.apple.cocoa.string"]},
        "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
        "AMActionVersion": "2.0.3",
        "AMApplication": ["Automator"],
        "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
        "ActionName": "Run Shell Script",
        "ActionParameters": {"COMMAND_STRING": script, "inputMethod": 1,
                             "shell": "/bin/sh", "CheckedForUserDefaultShell": True,
                             "source": ""},
        "AMParameterProperties": {key: {} for key in
                                  ("COMMAND_STRING", "inputMethod", "shell", "source",
                                   "CheckedForUserDefaultShell")},
        "BundleIdentifier": "com.apple.RunShellScript",
        "CFBundleVersion": "2.0.3",
        "Class Name": "RunShellScriptAction",
        "InputUUID": str(uuid4()), "OutputUUID": str(uuid4()), "UUID": str(uuid4()),
        "CanShowWhenRun": True,
    }
    metadata = {
        "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        "applicationBundleID": "com.apple.finder",
        "serviceApplicationBundleID": "com.apple.finder",
        "serviceApplicationPath": "/System/Library/CoreServices/Finder.app",
        "inputTypeIdentifier": "com.apple.Automator.fileSystemObject",
        "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
        "outputTypeIdentifier": "com.apple.Automator.nothing",
        "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
        "processesInput": 0, "serviceProcessesInput": 0,
    }
    workflow = {"AMDocumentVersion": "2", "AMApplicationVersion": "2.10",
                "actions": [{"action": action, "isViewVisible": True}],
                "connectors": {}, "workflowMetaData": metadata}
    info = {
        "CFBundleIdentifier": SERVICE_ID,
        "NSServices": [{
            "NSMenuItem": {"default": "Open in rgPDF", "zh_TW": "用 rgPDF 開啟"},
            "NSMessage": "runWorkflowAsService",
            "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
            "NSSendFileTypes": list(SERVICE_TYPES),
        }],
    }
    return info, workflow


def is_installed() -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            for path, placeholder in WINDOWS_KEYS + WINDOWS_FILE_KEYS:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path + r"\command") as key:
                    if winreg.QueryValueEx(key, "")[0] != windows_command(
                            placeholder, is_file=(path, placeholder) in WINDOWS_FILE_KEYS):
                        return False
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                    try:
                        selection = winreg.QueryValueEx(key, "MultiSelectModel")[0]
                    except FileNotFoundError:
                        selection = None
                    if selection != ("Document" if placeholder == "%1" else None):
                        return False
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        try:
            info = plistlib.loads((service_path() / "Contents" / "Info.plist").read_bytes())
            return (info.get("CFBundleIdentifier") == SERVICE_ID
                    and any(set(SERVICE_TYPES).issubset(service.get("NSSendFileTypes", []))
                            for service in info.get("NSServices", []))
                    and (service_path() / "Contents" / "document.wflow").is_file())
        except (OSError, ValueError, plistlib.InvalidFileException):
            return False
    return False


def set_enabled(enabled: bool, *, title: str = "Open in rgPDF") -> None:
    if sys.platform == "win32":
        import winreg
        for path, placeholder in WINDOWS_KEYS + WINDOWS_FILE_KEYS:
            if enabled:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, title)
                    winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ,
                                     subprocess.list2cmdline([launch_command()[0]]))
                    if placeholder == "%1":
                        # Explorer invokes the command for each selected folder;
                        # bootstrap forwards them into tabs of the same window.
                        winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Document")
                    else:
                        # A background menu has no selected items. Single hides
                        # this verb in Shell views such as Q-Dir's folder pane.
                        try:
                            winreg.DeleteValue(key, "MultiSelectModel")
                        except FileNotFoundError:
                            pass
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path + r"\command") as key:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, windows_command(
                        placeholder, is_file=(path, placeholder) in WINDOWS_FILE_KEYS))
            else:
                for owned in (path + r"\command", path):
                    try:
                        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, owned)
                    except FileNotFoundError:
                        pass
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    elif sys.platform == "darwin":
        root = service_path()
        contents = root / "Contents"
        info_path = contents / "Info.plist"
        if any(path.is_symlink() for path in
               (root, contents, info_path, contents / "document.wflow")):
            raise FileExistsError(f"Refusing to change a symlinked workflow: {root}")
        if root.exists():
            try:
                owned = plistlib.loads(info_path.read_bytes()).get("CFBundleIdentifier") == SERVICE_ID
            except (OSError, ValueError, plistlib.InvalidFileException):
                owned = False
            if not owned:
                raise FileExistsError(f"Refusing to replace an unrelated workflow: {root}")
        if enabled:
            info, workflow = finder_workflow()
            contents.mkdir(parents=True, exist_ok=True)
            info_path.write_bytes(plistlib.dumps(info))
            (contents / "document.wflow").write_bytes(plistlib.dumps(workflow))
        elif root.exists():
            if (set(root.iterdir()) != {contents}
                    or not set(contents.iterdir()) <= {info_path, contents / "document.wflow"}):
                raise FileExistsError(f"Workflow contains unrelated files: {root}")
            for path in (contents / "document.wflow", info_path):
                path.unlink(missing_ok=True)
            contents.rmdir()
            root.rmdir()
        # Refresh only the per-user service cache; Finder need not be killed.
        subprocess.run(["/System/Library/CoreServices/pbs", "-update"],
                       check=False, timeout=15, capture_output=True)
    else:
        raise OSError("File manager context menus are supported on Windows and macOS.")
