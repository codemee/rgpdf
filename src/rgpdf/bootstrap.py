# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Reuse the running instance before loading Qt, PDF engines or app settings."""
import multiprocessing
import json
import os
import subprocess
import sys
import time

from rgpdf.cli import parse_arguments
from rgpdf.instance import AlreadyRunning, InstanceError, LocalInstance


def _prepare_gui():
    deferred = getattr(sys, '_rgpdf_deferred_qt', None)
    if deferred is not None:
        del sys._rgpdf_deferred_qt
        function, args = deferred
        function(*args)


def _trace(event, started):
    path = os.environ.get('RGPDF_STARTUP_TRACE')
    if not path:
        return
    try:
        with open(path, 'a', encoding='utf-8') as stream:
            stream.write(json.dumps({'event': event, 'pid': os.getpid(), 'seconds': time.monotonic() - started,
                                     'heavy_modules': [name for name in sys.modules if name.startswith(
                                         ('PySide6', 'pymupdf', 'fitz', 'rgpdf.app', 'rgpdf.search'))]}) + '\n')
    except OSError:
        pass


def main(argv=None, *, _instance_factory=LocalInstance) -> int:
    multiprocessing.freeze_support()  # Frozen PDF workers must bypass GUI IPC.
    started = time.monotonic()
    arguments = parse_arguments(argv)
    if arguments.install_context_menu or arguments.remove_context_menu:
        from rgpdf.context_menu import set_enabled
        try:
            set_enabled(arguments.install_context_menu)
            return 0
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            return _error(str(exc))
    if arguments.new_window:
        _prepare_gui()
        from rgpdf.app import run_application
        return run_application(arguments)
    instance = _instance_factory()
    # Lexical normalization only: filesystem/network access belongs to the GUI.
    paths = [os.path.abspath(os.path.expanduser(path)) for path in arguments.paths if path]
    try:
        if instance.forward(paths):
            _trace('forwarded', started)
            return 0
        try:
            instance.start()
        except AlreadyRunning:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if instance.forward(paths):
                    _trace('forwarded', started)
                    return 0
                time.sleep(.05)
            raise InstanceError("rgPDF is already starting but could not receive the request. Please try again.")
        _trace('primary', started)
        _prepare_gui()
        from rgpdf.app import run_application
        return run_application(arguments, instance=instance)
    except OSError as exc:
        return _error(str(exc))
    finally:
        instance.close()


def _error(message):
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    elif sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "rgPDF", 0x10)
    return 1
