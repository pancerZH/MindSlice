"""Crash-safe filesystem helpers (atomic writes, durable moves, directory walks)."""

from __future__ import annotations

import errno
import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterator


def fsync_dir(path: Path) -> None:
    """fsync a directory so renames/unlinks inside it are durable (best effort on non-POSIX)."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    fsync_dir(path.parent)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def durable_move(src: Path, dst: Path) -> None:
    """Move ``src`` over ``dst`` atomically, falling back to copy+replace across devices."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(src, dst)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        atomic_write_bytes(dst, src.read_bytes())
        os.unlink(src)
        fsync_dir(src.parent)
    fsync_dir(dst.parent)


def unlink_if_exists(path: Path) -> bool:
    try:
        os.unlink(path)
    except FileNotFoundError:
        return False
    fsync_dir(path.parent)
    return True


def prune_empty_dirs(root: Path, start: Path) -> None:
    """Remove empty directories from ``start`` upward, stopping at (and keeping) ``root``."""
    root = root.resolve()
    current = start.resolve()
    while current != root and root in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def iter_markdown(root: Path, exclude: tuple[Path, ...] = ()) -> Iterator[tuple[str, os.stat_result]]:
    """Yield ``(relative_posix_path_without_md, stat)`` for card files under ``root``.

    Hidden files/directories (``.git``, ``.cache``, ``.manifest.json``...) are skipped,
    as are any directories listed in ``exclude`` (e.g. a nested ``staging/``).
    """
    if not root.is_dir():
        return
    excluded = {os.path.abspath(p) for p in exclude}
    visited = {os.path.realpath(root)}  # guards against directory symlink loops
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir(follow_symlinks=True):
                    real = os.path.realpath(entry.path)
                    if os.path.abspath(entry.path) not in excluded and real not in visited:
                        visited.add(real)
                        stack.append(Path(entry.path))
                    continue
                if not entry.name.endswith(".md") or not entry.is_file(follow_symlinks=True):
                    continue
                st = entry.stat(follow_symlinks=True)
            except OSError:
                continue
            rel = Path(entry.path).relative_to(root).as_posix()[:-3]
            yield rel, st


def clear_directory(path: Path) -> None:
    if not path.exists():
        return
    for entry in path.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    fsync_dir(path)
