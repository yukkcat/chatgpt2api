from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator


_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.Lock] = {}


def _process_lock(path: Path) -> threading.Lock:
    key = os.path.normcase(str(path.resolve()))
    with _LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.Lock())


def _try_lock(handle: BinaryIO) -> bool:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def _unlock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def interprocess_lock(
    path: Path,
    *,
    timeout_seconds: float = 30.0,
    poll_seconds: float = 0.05,
) -> Iterator[None]:
    """Serialize a critical section across threads and local processes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    local_lock = _process_lock(path)
    acquired_local = local_lock.acquire(timeout=timeout_seconds)
    if not acquired_local:
        raise TimeoutError(f"timed out waiting for storage lock: {path}")

    handle: BinaryIO | None = None
    locked = False
    try:
        handle = path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()

        deadline = time.monotonic() + timeout_seconds
        while not (locked := _try_lock(handle)):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for storage lock: {path}")
            time.sleep(poll_seconds)
        yield
    finally:
        try:
            if handle is not None:
                try:
                    if locked:
                        _unlock(handle)
                finally:
                    handle.close()
        finally:
            local_lock.release()
