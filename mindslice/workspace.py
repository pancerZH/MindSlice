"""The MindSlice workspace: mount table + overlay + staging + disposable index.

All nine primitives are methods on :class:`Workspace`:

* Group A (online, also exposed over MCP): ``manifest``, ``search``, ``read``, ``write``
  (plus ``boot``: the always-loaded cards, which ``manifest`` also returns)
* Group B (slice management):              ``mount`` / ``unmount``, ``validate``, ``pack`` (and ``bake``:
  a new version of a mounted slice, with overlay cards baked in, mounted in the old one's place)
* Group C (transactional sandbox):         ``diff``, ``apply`` / ``discard``

Every operation runs under ``.cache/workspace.lock`` (``LOCK_SH`` for reads,
``LOCK_EX`` for writes). Before serving any request the workspace finishes an
interrupted ``apply()`` (if ``staging/.apply_journal.json`` exists) and
re-indexes files whose ``(mtime_ns, size)`` changed, upgrading to ``LOCK_EX``
only when there is maintenance to do.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from . import bake as bake_mod, boot as boot_mod, packer, query, staging as staging_mod, validation, writer
from .addressing import alias_from_name, normalize_alias
from .config import (
    MOUNTS_FILE,
    Mount,
    MountTable,
    load_mounts,
    load_slice_manifest,
    portable_path,
    save_mounts,
)
from .errors import MountError, NotFoundError, WorkspaceNotFoundError
from .index import FRONTMATTER_CODES, Index, SyncStats
from .lineage import FollowSpec
from .locking import WorkspaceLock
from .staging import StagingArea

CACHE_DIR = ".cache"
INDEX_FILE = "index.sqlite"
LOCK_FILE = "workspace.lock"
STAGING_DIR = "staging"
SLICES_DIR = "slices"


class Workspace:
    def __init__(self, root: str | os.PathLike[str], *, create: bool = False, lock_timeout: float = 30.0) -> None:
        self.root = Path(os.path.abspath(Path(root).expanduser()))
        if not (self.root / MOUNTS_FILE).is_file():
            if not create:
                raise WorkspaceNotFoundError(f"{self.root} is not a MindSlice workspace (no {MOUNTS_FILE}); run `mindslice init`")
            self._bootstrap()
        self.cache_dir = self.root / CACHE_DIR
        self.staging = StagingArea(self.root / STAGING_DIR)
        self.lock = WorkspaceLock(self.cache_dir / LOCK_FILE, timeout=lock_timeout)
        self._index: Index | None = None
        self._table: MountTable | None = None
        self.last_sync: SyncStats | None = None
        self.last_recovery: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def init(cls, root: str | os.PathLike[str], **kwargs: Any) -> "Workspace":
        """Create (or open) a workspace with an empty overlay and default mount table."""
        return cls(root, create=True, **kwargs)

    @classmethod
    def discover(cls, start: str | os.PathLike[str] | None = None, **kwargs: Any) -> "Workspace":
        """Find the nearest enclosing workspace (directory containing ``mounts.toml``)."""
        current = Path(os.path.abspath(Path(start or os.getcwd()).expanduser()))
        for candidate in (current, *current.parents):
            if (candidate / MOUNTS_FILE).is_file():
                return cls(candidate, **kwargs)
        raise WorkspaceNotFoundError(f"no {MOUNTS_FILE} found in {current} or any parent directory")

    def _bootstrap(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in ("overlay", STAGING_DIR, SLICES_DIR, CACHE_DIR):
            (self.root / sub).mkdir(exist_ok=True)
        gitignore = self.root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(f"{CACHE_DIR}/\n", encoding="utf-8")
        table = load_mounts(self.root)  # defaults: ./overlay @overlay precedence=100 role=runtime
        save_mounts(self.root, table)

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    @property
    def index(self) -> Index:
        if self._index is None:
            self._index = Index(self.cache_dir / INDEX_FILE)
        return self._index

    def close(self) -> None:
        if self._index is not None:
            self._index.close()
            self._index = None
        self.lock.close()

    def __enter__(self) -> "Workspace":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Workspace({str(self.root)!r})"

    # ------------------------------------------------------------------
    # mount table / maintenance
    # ------------------------------------------------------------------
    def table(self) -> MountTable:
        if self._table is None:
            self._table = load_mounts(self.root)
        return self._table

    def _reload_table(self) -> MountTable:
        self._table = load_mounts(self.root)
        return self._table

    def _exclude(self) -> list[Path]:
        return [self.staging.root, self.cache_dir]

    def _sync(self, table: MountTable | None = None, verify: bool = False) -> SyncStats:
        stats = self.index.sync(table or self.table(), self._exclude(), verify=verify)
        self.last_sync = stats
        return stats

    def _recover(self, table: MountTable) -> None:
        journal = self.staging.read_journal()
        if journal is None:
            return
        if journal.get("corrupt"):
            moved_to = self.staging.quarantine_journal()
            self.last_recovery = {"recovered": False, "corrupt_journal": str(moved_to)}
            return
        report = staging_mod.replay(self, table, journal)
        report["recovered"] = True
        self.last_recovery = report

    def _needs_maintenance(self, table: MountTable) -> bool:
        return self.staging.has_journal() or self.index.is_stale(table, self._exclude())

    @contextmanager
    def _reading(self) -> Iterator[MountTable]:
        """Shared lock; upgrades to exclusive only if a journal or stale files need handling."""
        with self.lock.shared():
            table = self._reload_table()
            if not self._needs_maintenance(table):
                yield table
                return
        with self.lock.exclusive():
            table = self._reload_table()
            self._recover(table)
            self._sync(table)
            yield table

    @contextmanager
    def _writing(self, sync: bool = True) -> Iterator[MountTable]:
        with self.lock.exclusive():
            table = self._reload_table()
            self._recover(table)
            if sync:
                self._sync(table)
            yield table

    # ------------------------------------------------------------------
    # Group A: online read/write
    # ------------------------------------------------------------------
    def manifest(self, limit: int = 20, offset: int = 0, max_folders_per_mount: int = 10,
                 include_overview: bool = False, include_always: bool = True) -> dict[str, Any]:
        return query.manifest(self, limit, offset, max_folders_per_mount, include_overview, include_always)

    def boot(self) -> dict[str, Any]:
        """The always-loaded cards (``load = "always"``), resolved and composed, for a session's start."""
        return boot_mod.boot(self)

    def search(self, query_text: str, source: str | Sequence[str] | None = None,
               tags: str | Sequence[str] | None = None, k: int = 10, offset: int = 0,
               max_neighbors: int = 3, follow_supersedes: FollowSpec = True) -> dict[str, Any]:
        return query.search(self, query_text, source, tags, k, offset, max_neighbors, follow_supersedes)

    def read(self, address: str, follow_supersedes: FollowSpec = True, max_backlinks: int = 10,
             backlinks_offset: int = 0, max_extensions: int = 5, extensions_offset: int = 0) -> dict[str, Any]:
        return query.read(self, address, follow_supersedes, max_backlinks, backlinks_offset,
                          max_extensions, extensions_offset)

    def write(self, id: str, op: str = "create", content: Any = None, summary: str | None = None,
              title: str | None = None, tags: Sequence[str] | None = None, aliases: Sequence[str] | None = None,
              extends: Sequence[str] | None = None, supersedes: Sequence[str] | None = None,
              stage: bool | None = None, if_match: str | None = None, load: str | None = None) -> dict[str, Any]:
        """``stage=None`` stages changes to the always-loaded context for approval (see ``boot``)."""
        return writer.write(self, id, op, content, summary, title, tags, aliases, extends, supersedes, stage,
                            if_match, load)

    # ------------------------------------------------------------------
    # Group B: slice management, linting & packaging
    # ------------------------------------------------------------------
    def mount(self, path: str | os.PathLike[str], alias: str | None = None, precedence: int = 50,
              role: str = "baseline", retire_overlay: bool = True) -> dict[str, Any]:
        """Mount a read-only slice directory.

        Relative paths are resolved against the current directory, falling back to the
        workspace root. ``mounts.toml`` stores ``./relative`` paths for slices inside the workspace.

        Any directory of Markdown works as is: notes without frontmatter, or with legacy ``---`` YAML,
        are indexed without conversion, and without ``alias`` or a ``slice.toml`` alias the directory
        name becomes one (``My Notes`` -> ``@My-Notes``).

        ``retire_overlay`` (default): ``@overlay`` cards this slice holds unchanged, as ``pack()``
        exported them, are removed from the overlay so they don't shadow it, and references to them
        from the overlay cards that stay are rewritten to the slice (``packer.retire_packed_copies``).
        """
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = target.absolute() if target.is_dir() else self.root / target
        target = Path(os.path.abspath(target))
        if not target.is_dir():
            raise MountError(f"{target} is not a directory", path=str(target))
        if isinstance(precedence, bool) or not isinstance(precedence, int):
            raise MountError("precedence must be an integer")
        if not isinstance(role, str) or not role.strip():
            raise MountError("role must be a non-empty string")
        sm = load_slice_manifest(target)
        if alias or sm.alias:
            alias = normalize_alias(alias or sm.alias)
        else:  # a plain folder: its name, made a valid alias
            alias = alias_from_name(target.name.removesuffix(".slice"))
        with self._writing() as table:
            if alias == table.overlay.alias or table.get(alias) is not None:
                raise MountError(f"alias {alias} is already mounted", alias=alias)
            for m in table.all():
                if m.root == target:
                    raise MountError(f"{target} is already mounted as {m.alias}", alias=m.alias)
            if target in (self.staging.root, self.cache_dir) or self.cache_dir in target.parents:
                raise MountError("cannot mount MindSlice internal directories")
            new = Mount(alias, portable_path(self.root, target), precedence, role.strip(), "slice", target)
            new_table = MountTable(table.overlay, [*table.mounts, new])
            save_mounts(self.root, new_table)
            table = self._reload_table()
            stats = self._sync(table)
            retired = packer.retire_packed_copies(self, table, alias) if retire_overlay else {}
            if retired:
                self._sync(table)
            mounted = {m.alias for m in new_table.all()}
            missing = []
            for dep in sm.dependencies:
                try:
                    if normalize_alias(dep) not in mounted:
                        missing.append(dep)
                except ValueError:
                    missing.append(dep)
            rows = [r for r in self.index.all_cards(alias) if not r["is_overview"]]
            result: dict[str, Any] = {
                "alias": alias, "path": new.path, "precedence": precedence, "role": new.role,
                "cards": len(rows), "sync": stats.to_dict(),
            }
            plain = sum(1 for r in rows if r["has_frontmatter"] == FRONTMATTER_CODES[None])
            yaml = sum(1 for r in rows if r["has_frontmatter"] == FRONTMATTER_CODES["yaml"])
            if plain or yaml:  # indexed as is: title from the heading or file name, summary from the first paragraph
                result["formats"] = {"toml": len(rows) - plain - yaml, "yaml": yaml, "plain": plain}
            result.update(retired)
            if missing:
                result["missing_dependencies"] = missing
            if sm.errors:
                result["manifest_errors"] = sm.errors
            always = [c for c in boot_mod.snapshot(self, self.table())["cards"]
                      if c["mount"] == alias or c.get("redirected_from", "").startswith(alias + "/")]
            if always:
                result["always_loaded"] = always
            return result

    def unmount(self, alias: str) -> dict[str, Any]:
        alias = normalize_alias(alias)
        with self._writing() as table:
            if alias == table.overlay.alias:
                raise MountError(f"{alias} is the writable overlay and cannot be unmounted")
            if table.get(alias) is None:
                raise NotFoundError(f"{alias} is not mounted", alias=alias)
            new_table = MountTable(table.overlay, [m for m in table.mounts if m.alias != alias])
            save_mounts(self.root, new_table)
            stats = self._sync(self._reload_table())
            return {"alias": alias, "removed_cards": stats.removed, "sync": stats.to_dict()}

    def validate(self, slice_path: str | os.PathLike[str] | None = None, rebuild_index: bool = False) -> dict[str, Any]:
        return validation.validate(self, slice_path, rebuild_index)

    def bake(self, alias: str, output_path: str | os.PathLike[str] | None = None, prefix: str | None = None,
             tags: str | Sequence[str] | None = None, include_deps: bool = False, dry_run: bool = False) -> dict[str, Any]:
        """Bake ``@overlay`` cards into a new version of the mounted slice ``alias`` and mount it in its place.

        The old folder is left untouched (and unmounted); ``output_path`` defaults to ``slices/<name>.slice``.
        """
        return bake_mod.bake(self, alias, output_path, prefix, tags, include_deps, dry_run)

    def pack(self, output_path: str | os.PathLike[str], prefix: str | None = None,
             tags: str | Sequence[str] | None = None, include_deps: bool = False, **kwargs: Any) -> dict[str, Any]:
        return packer.pack(self, output_path, prefix, tags, include_deps, **kwargs)

    # ------------------------------------------------------------------
    # Group C: transactional sandbox
    # ------------------------------------------------------------------
    def diff(self, scope: str = "staging") -> dict[str, Any]:
        return staging_mod.diff(self, scope)

    def apply(self) -> dict[str, Any]:
        return staging_mod.apply(self)

    def discard(self) -> dict[str, Any]:
        return staging_mod.discard(self)
