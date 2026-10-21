"""Persist KITE codebook changes through a single integration boundary."""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path


DEFAULT_TIMEOUT = 600.0


_POLL_INTERVAL = 0.1

_thread_locks: dict[str, threading.Lock] = {}
_registry_guard = threading.Lock()


class WriteLockTimeout(RuntimeError):
    pass


def _thread_lock_for(key: str) -> threading.Lock:
    with _registry_guard:
        lock = _thread_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _thread_locks[key] = lock
        return lock


if os.name == "nt":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


@contextmanager
def write_lock(codebook_path: str | Path, timeout: float = DEFAULT_TIMEOUT):
    path = Path(codebook_path)
    key = str(path.resolve())
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    deadline = time.monotonic() + timeout
    thread_lock = _thread_lock_for(key)


    if not thread_lock.acquire(timeout=max(timeout, 0.0)):
        raise WriteLockTimeout(f'Timed out waiting for the process write lock: {path}')

    fd = None
    try:
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        while True:
            if _try_lock(fd):
                break
            if time.monotonic() >= deadline:
                raise WriteLockTimeout(f'Timed out waiting for the file write lock: {lock_path}')
            time.sleep(_POLL_INTERVAL)

        try:
            yield path
        finally:
            _unlock(fd)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        thread_lock.release()
