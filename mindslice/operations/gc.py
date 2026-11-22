"""``gc()``: delete what nothing uses any more: older versions of mounted slices and leftovers of interrupted writes.

Runs under the exclusive lock, after recovery. Every writer creates its temporary files and directories only
while holding that lock, so any that still exist then are leftovers of a killed process. ``.cache/`` is left
alone (disposable, and the MCP server's client record is written there without the lock).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..model.addressing import normalize_alias
from ..storage.config import load_slice_manifest
from ..storage.fsutil import fsync_dir

if TYPE_CHECKING:  # pragma: no cover
    from ..workspace import Workspace

# tempfile names end in 8 characters from [a-z0-9_].
TEMP_FILE = re.compile(r"\..+\.[a-z0-9_]{8}\.tmp")  # atomic_write_bytes
TEMP_SLICE = re.compile(r"\.(?:bake-[a-z0-9_]{8}|.+\.[a-z0-9_]{8})")  # bake and archive staging beside the output


def _alias(path: Path) -> str | None:
    """The alias in the directory's ``slice.toml``: bake always writes one, a folder of notes may have none."""
    alias = load_slice_manifest(path).alias
    try:
        return normalize_alias(alias) if alias else None
    except ValueError:
        return None


def _temp_files(root: Path, recursive: bool) -> list[Path]:
    if not root.is_dir():
        return []
    if not recursive:
        return sorted(p for p in root.iterdir() if TEMP_FILE.fullmatch(p.name) and p.is_file() and not p.is_symlink())
    found = []
    for directory, names, files in os.walk(root):
        names[:] = [n for n in names if n != ".git"]
        found += [Path(directory, f) for f in files if TEMP_FILE.fullmatch(f)]
    return sorted(found)


def _size(path: Path) -> int:
    if path.is_symlink() or not path.is_dir():
        return path.lstat().st_size
    return sum(p.lstat().st_size for p in path.rglob("*") if not p.is_dir() or p.is_symlink())


def gc(ws: "Workspace", dry_run: bool) -> dict[str, Any]:
    with ws._writing(sync=False) as table:
        mounted = {m.alias for m in table.all()}
        in_use = [m.root.resolve() for m in table.all()] + [p.resolve() for p in ws._exclude()]
        old, unmounted, temporary = [], [], []
        slices = ws.root / "slices"
        for entry in sorted(slices.iterdir()) if slices.is_dir() else []:
            if entry.name.startswith("."):
                if TEMP_SLICE.fullmatch(entry.name):
                    temporary.append(entry)
                continue
            if entry.is_symlink() or not entry.is_dir():
                continue
            real = entry.resolve()
            if any(real == p or real in p.parents or p in real.parents for p in in_use):
                continue
            alias = _alias(entry)
            # Another directory serves this alias: an older version, or the output of a bake killed before it
            # was mounted. A slice whose alias nothing serves was unmounted on purpose, and a folder without a
            # slice.toml alias was not made by bake: both stay.
            (old if alias in mounted else unmounted).append({"path": str(entry), "alias": alias})
        temporary += _temp_files(ws.root, False) + _temp_files(ws.history.root, False)
        temporary += _temp_files(table.overlay.root, True) + _temp_files(ws.staging.root, True)
        doomed = [Path(item["path"]) for item in old] + temporary
        size = sum(_size(p) for p in doomed)
        if not dry_run:
            for path in doomed:
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            for parent in {p.parent for p in doomed}:
                fsync_dir(parent)
        return {"dry_run": dry_run, "old_versions": old, "temporary": [str(p) for p in temporary],
                "kept_unmounted": unmounted, "bytes": size}


def render_gc(result: dict[str, Any]) -> str:
    verb = "Would remove" if result["dry_run"] else "Removed"
    lines = [f"{verb} old version of {item['alias']}: {item['path']}" for item in result["old_versions"]]
    lines += [f"{verb} leftover: {path}" for path in result["temporary"]]
    lines += [f"Kept unmounted slice ({item['alias'] or 'no slice.toml alias'}): {item['path']}"
              for item in result["kept_unmounted"]]
    count = len(result["old_versions"]) + len(result["temporary"])
    lines.append(f"{verb} {count} item(s), {result['bytes']} bytes." if count else "Nothing to remove.")
    return "\n".join(lines) + "\n"
