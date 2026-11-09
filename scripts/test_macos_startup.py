# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Wait for the real GUI event loop, then verify lightweight App forwarding."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def events(path: Path):
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return []
    result = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except ValueError:
            pass  # A concurrent append may not yet be complete.
    return result


def wait_ready(process, trace: Path, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('App exited before its GUI was ready')
        if any(item.get('event') == 'gui-ready' and item.get('pid') == process.pid for item in events(trace)):
            return
        time.sleep(.1)
    raise TimeoutError('App GUI was not ready within the startup timeout')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='rgpdf-macos-smoke-') as directory:
        folder = Path(directory) / 'folder with spaces 中文'
        folder.mkdir()
        file = folder / 'document.pdf'
        file.touch()
        trace = Path(directory) / 'trace.jsonl'
        env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'RGPDF_STARTUP_TRACE': str(trace)}
        started = time.monotonic()
        process = subprocess.Popen([str(args.binary.resolve())], env=env)
        try:
            wait_ready(process, trace)
            print(f'App GUI ready in {time.monotonic() - started:.2f}s', flush=True)
            subprocess.run([str(args.binary.resolve()), '--', str(file)], env=env, check=True, timeout=10)
            forwarded = [item for item in events(trace) if item.get('event') == 'forwarded']
            if len(forwarded) != 1 or forwarded[0]['heavy_modules']:
                raise RuntimeError('Forwarding failed or imported GUI/PDF modules')
            if process.poll() is not None:
                raise RuntimeError('Primary App exited during forwarding')
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
