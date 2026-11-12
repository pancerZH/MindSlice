"""Reader/writer workspace lock on ``.cache/workspace.lock``.

POSIX uses ``fcntl.flock`` (``LOCK_SH`` for readers, ``LOCK_EX`` for writers).
On Windows an optional ``msvcrt`` adapter takes a byte-range lock; it cannot
express shared locks, so every acquisition is exclusive there.

The lock is re-entrant per ``WorkspaceLock`` instance and serializes threads of
the same process with an ``RLock``. Requesting ``exclusive`` while holding
``shared`` converts the lock (flock conversion is not atomic, so callers must
re-check state after upgrading — the workspace does).
"""

from __future__ import annotations

import errno
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..errors import LockTimeoutError

try:  # POSIX
    import fcntl

    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]
    _HAVE_FCNTL = False
    import msvcrt  # type: ignore[import-not-found]

SHARED = "shared"
EXCLUSIVE = "exclusive"
_CONTENDED = {errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK, errno.EDEADLK}


class WorkspaceLock:
    def __init__(self, path: Path, timeout: float = 30.0) -> None:
        self.path = path
        self.timeout = timeout
        self._fd: int | None = None
        self._mode: str | None = None
        self._depth = 0
        self._thread_lock = threading.RLock()

    # -- low level -------------------------------------------------------
    def _open(self) -> int:
        if self._fd is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        return self._fd

    def _acquire(self, mode: str) -> None:
        fd = self._open()
        deadline = time.monotonic() + self.timeout
        delay = 0.005
        while True:
            try:
                if _HAVE_FCNTL:
                    flag = fcntl.LOCK_SH if mode == SHARED else fcntl.LOCK_EX
                    fcntl.flock(fd, flag | fcntl.LOCK_NB)
                else:  # pragma: no cover - Windows
                    if self._mode is None:
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                self._mode = mode
                return
            except OSError as exc:
                if exc.errno not in _CONTENDED:
                    raise
                if time.monotonic() >= deadline:
                    raise LockTimeoutError(f"timed out waiting for {mode} lock on {self.path}") from None
                time.sleep(delay)
                delay = min(delay * 2, 0.1)

    def _release(self) -> None:
        if self._fd is None or self._mode is None:
            return
        if _HAVE_FCNTL:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        else:  # pragma: no cover - Windows
            os.lseek(self._fd, 0, os.SEEK_SET)
            msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
        self._mode = None

    # -- public API ------------------------------------------------------
    @property
    def mode(self) -> str | None:
        return self._mode

    @contextmanager
    def hold(self, mode: str) -> Iterator[str]:
        """Hold the lock in ``mode`` (re-entrant; upgrades shared -> exclusive when nested)."""
        with self._thread_lock:
            previous = self._mode
            if previous is None:
                self._acquire(mode)
            elif previous == SHARED and mode == EXCLUSIVE:
                self._acquire(EXCLUSIVE)
            self._depth += 1
            try:
                yield self._mode or mode
            finally:
                self._depth -= 1
                if previous is None:
                    self._release()
                elif previous == SHARED and self._mode == EXCLUSIVE:
                    self._acquire(SHARED)

    def shared(self):
        return self.hold(SHARED)

    def exclusive(self):
        return self.hold(EXCLUSIVE)

    def close(self) -> None:
        with self._thread_lock:
            if self._depth:
                return
            self._release()
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
