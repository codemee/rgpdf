# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Early per-user IPC using bounded JSON messages, without GUI dependencies."""
from __future__ import annotations

import hashlib
import json
from multiprocessing.connection import Connection, Listener
import os
from queue import Empty, Full, Queue
import socket
import stat
import sys
import tempfile
from threading import Event, Thread

LIMIT = 65536
PROTOCOL = "rgpdf-open-1"


class InstanceError(OSError):
    pass


class AlreadyRunning(InstanceError):
    pass


def default_address() -> str:
    identity = os.path.normcase(os.path.expanduser("~"))
    digest = hashlib.sha256(identity.encode()).hexdigest()[:20]
    if sys.platform == "win32":
        return rf"\\.\pipe\rgpdf-{digest}"
    return os.path.join(tempfile.gettempdir(), f"rgpdf-{os.getuid()}-{digest}.sock")


def _connect(address: str):
    if sys.platform == "win32":
        # CPython's PipeClient retries busy pipes for ~20 seconds. Make one
        # bounded attempt instead; bootstrap owns the short retry policy.
        import _winapi
        from multiprocessing.connection import PipeConnection
        _winapi.WaitNamedPipe(address, 100)
        handle = _winapi.CreateFile(address, _winapi.GENERIC_READ | _winapi.GENERIC_WRITE,
                                   0, _winapi.NULL, _winapi.OPEN_EXISTING,
                                   _winapi.FILE_FLAG_OVERLAPPED, _winapi.NULL)
        try:
            _winapi.SetNamedPipeHandleState(handle, _winapi.PIPE_READMODE_MESSAGE, None, None)
            return PipeConnection(handle)
        except BaseException:
            _winapi.CloseHandle(handle)
            raise
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(.3)
        sock.connect(address)
        sock.setblocking(True)
        return Connection(sock.detach())
    finally:
        sock.close()


def _send(connection, value):
    data = json.dumps(value, ensure_ascii=False).encode("utf-8")
    if len(data) > LIMIT:
        raise InstanceError("Too many or overly long paths")
    connection.send_bytes(data)


def _receive(connection, timeout=.7):
    if not connection.poll(timeout):
        raise InstanceError("The running rgPDF did not respond in time")
    return json.loads(connection.recv_bytes(LIMIT).decode("utf-8"))


class LocalInstance:
    def __init__(self, address=None):
        self.address = address or default_address()
        self.requests = Queue(maxsize=128)
        self._listener = None
        self._thread = None
        self._lock = None
        self._stop = Event()
        self._accepting = Event()
        self._accepting.set()

    def forward(self, paths) -> bool:
        try:
            connection = _connect(self.address)
        except OSError:
            return False
        try:
            with connection:
                hello = _receive(connection)
                if not isinstance(hello, dict) or hello.get("protocol") != PROTOCOL:
                    raise InstanceError("Unexpected local IPC endpoint")
                if sys.platform == "win32" and isinstance(hello.get("pid"), int):
                    import ctypes
                    ctypes.windll.user32.AllowSetForegroundWindow(hello["pid"])
                _send(connection, {"protocol": PROTOCOL, "paths": paths})
                reply = _receive(connection)
                if not isinstance(reply, dict) or reply.get("accepted") is not True:
                    raise InstanceError("The running rgPDF is closing or cannot accept more requests")
                return True
        except (EOFError, ValueError, UnicodeError) as exc:
            raise InstanceError("Invalid response from the running rgPDF") from exc

    def start(self):
        if sys.platform != "win32":
            import fcntl
            flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            self._lock = os.fdopen(os.open(self.address + ".lock", flags, 0o600), "r+b")
            try:
                info = os.fstat(self._lock.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                    raise InstanceError("Unexpected IPC lock ownership")
                fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                self._lock.close(); self._lock = None
                raise AlreadyRunning("rgPDF is already starting") from exc
            if os.path.lexists(self.address):
                info = os.lstat(self.address)
                if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                    raise InstanceError("Unexpected IPC socket ownership")
                os.unlink(self.address)  # Only while holding the owner lock.
        try:
            self._listener = Listener(self.address, family="AF_PIPE" if sys.platform == "win32" else "AF_UNIX")
            if sys.platform != "win32":
                os.chmod(self.address, 0o600)
        except OSError as exc:
            if self._lock is not None:
                self._lock.close(); self._lock = None
            raise AlreadyRunning("rgPDF endpoint already exists or is unavailable") from exc
        self._thread = Thread(target=self._serve, name="rgpdf-local-open", daemon=True)
        self._thread.start()

    def _serve(self):
        while not self._stop.is_set():
            try:
                with self._listener.accept() as connection:
                    if self._stop.is_set():
                        break
                    _send(connection, {"protocol": PROTOCOL, "pid": os.getpid()})
                    request = _receive(connection, timeout=2)
                    paths = request.get("paths") if isinstance(request, dict) else None
                    valid = (isinstance(request, dict) and request.get("protocol") == PROTOCOL
                             and isinstance(paths, list) and len(paths) <= 256
                             and all(isinstance(path, str) and "\0" not in path for path in paths))
                    accepted = False
                    if valid and self._accepting.is_set():
                        try:
                            self.requests.put_nowait(paths)
                            accepted = True
                        except Full:
                            pass
                    _send(connection, {"accepted": accepted})
            except (OSError, EOFError, ValueError, UnicodeError):
                if self._stop.is_set():
                    break

    def pending(self):
        while True:
            try:
                yield self.requests.get_nowait()
            except Empty:
                return

    def stop_accepting(self):
        self._accepting.clear()

    def close(self):
        self.stop_accepting()
        self._stop.set()
        if self._listener is not None:
            try:
                _connect(self.address).close()  # Wake a blocked accept().
            except OSError:
                pass
            if self._thread is not None:
                self._thread.join(2.5)
            self._listener.close()
            self._listener = None
        if self._lock is not None:
            self._lock.close(); self._lock = None
