"""``bake()``: create or update a slice and mount it under the requested alias.

A new alias requires an explicit ``prefix`` selecting overlay cards. ``bake(alias)`` without a
prefix builds the next version of a mounted slice: a copy of its folder (``.git`` excluded) plus the
overlay cards, at a new path. The new folder then takes over the mount (same alias, precedence and role, so every
``@alias/...`` reference keeps resolving), the overlay copies are retired, and the old folder is left
exactly as it was: no longer mounted, and a way back (``mount`` it again). It is a curation step for
the slice's owner (CLI and Python, never an agent tool).

Which cards: with ``prefix`` / ``tags``, the overlay cards they select; without, the overlay cards
that belong to the slice: those that extend or supersede one of its cards, or sit
at the same path as one. ``include_deps`` pulls in overlay cards the selection references.

How each card is written into the new slice:

* references to the slice itself (``@alias/x``) and to other baked cards become slice-relative
  (``x``); references to other mounts stay qualified and are added to ``slice.toml`` dependencies;
* a card that supersedes the slice card at its own path, or shadows it, replaces that file (the
  card's ``supersedes`` drops the reference to itself); a superseded card at another path stays,
  as the route that forwards its hits;
* a card that *extends* the slice card at its own path can't replace it without losing the
  baseline: bake refuses it (``BakeConflictError``) until it is consolidated into one card.

The new slice's ``slice.toml`` version is bumped (``1.2.3`` -> ``1.2.4``) when it has that form. Its
default path is ``<workspace>/slices/<name>.slice``, or ``<name>-2.slice``, ``-3`` ... when taken.
``dry_run`` reports the plan and writes nothing. The new folder is built in a temporary directory and
moved into place whole; the mount table is switched in one atomic write.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from ..model.addressing import format_address, normalize_alias, resolve_ref
from .archive import archive_format, write_archive
from ..model.card import normalize_newlines, parse_card, truncate
from ..storage.config import (
    DESCRIPTION_CHARS,
    MOUNTS_FILE,
    OVERVIEW_PATH,
    SLICE_FILE,
    Mount,
    MountTable,
    SliceManifest,
    dump_slice_manifest,
    load_slice_manifest,
    portable_path,
    dump_mounts,
)
from ..errors import AlreadyExistsError, BakeConflictError, InvalidAddressError, InvalidArgumentsError, MountError, NotFoundError
from ..storage.fsutil import fsync_dir
from ..storage.history import event, file_action, file_sha
from ..model.text import fold
from .slice_transfer import dependency_closure, export_text, overlay_cards, retire_overlay_paths, rewrite_refs
from ..operations.validation import validate_slice_dir
from ..model.card import reassemble

if TYPE_CHECKING:  # pragma: no cover
    from ..workspace import Workspace


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def bump_version(version: str) -> str:
    m = _SEMVER_RE.match(version.strip())
    return f"{m.group(1)}.{m.group(2)}.{int(m.group(3)) + 1}" if m else version


def default_output(ws: "Workspace", alias: str, mount: Mount | None) -> Path:
    """``<workspace>/slices/<name>.slice``, or the first free ``<name>-N.slice``."""
    stem = re.sub(r"-\d+$", "", mount.root.name.removesuffix(".slice")) if mount else alias.lstrip("@")
    stem = stem or "slice"
    slices = ws.root / "slices"
    n = 1
    while True:
        candidate = slices / (f"{stem}.slice" if n == 1 else f"{stem}-{n}.slice")
        if (mount is None or candidate != mount.root) and not candidate.exists():
            return candidate
        n += 1


def bake(
    ws: "Workspace",
    alias: str,
    output_path: str | os.PathLike[str] | None = None,
    prefix: str | None = None,
    tags: str | Sequence[str] | None = None,
    include_deps: bool = False,
    dry_run: bool = False,
    *,
    name: str | None = None,
    description: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    alias = normalize_alias(alias)
    tag_set = {fold(t) for t in ([tags] if isinstance(tags, str) else (tags or [])) if fold(t)}
    if prefix is not None:
        prefix = prefix.strip().lstrip("./").lstrip("/")
    with ws._writing() as table:
        mount = table.get(alias)
        overlay = table.overlay
        if mount is None and prefix is None:
            raise InvalidArgumentsError(f"--prefix is required to create {alias}; use prefix='' to select all overlay cards",
                                        alias=alias)
        if alias == overlay.alias:
            raise MountError(f"bake moves {overlay.alias} cards into a slice; name the slice, not {alias}")
        if mount and not mount.root.is_dir():
            raise MountError(f"{alias}: {mount.root} is not a directory", alias=alias)
        idx = ws.index
        cats = idx.catalogs()
        cards = overlay_cards(ws, table)
        slice_paths = {r["path"] for r in idx.all_cards(alias)}

        def targets_slice(raw: str) -> str | None:
            res = resolve_ref(raw, overlay.alias, cats)
            return res.path if res.resolved and res.mount == alias else None

        def selected(path: str, parsed) -> bool:
            if path == OVERVIEW_PATH and (mount or prefix or tag_set):
                return False
            if prefix is not None or tag_set or mount is None:
                return (not prefix or path.startswith(prefix)) and tag_set <= {fold(t) for t in parsed.tags}
            return path in slice_paths or any(targets_slice(r) for r in parsed.extends + parsed.supersedes)

        chosen = sorted(p for p, (_, parsed) in cards.items() if selected(p, parsed))
        if not chosen:
            how = f"prefix={prefix!r} tags={sorted(tag_set)}" if (prefix is not None or tag_set) else (
                f"none extends, supersedes or shares a path with a card in {alias}; pass prefix or tags to choose")
            raise NotFoundError(f"no {overlay.alias} cards to bake into {alias} ({how})", alias=alias)
        included, pulled, external, warnings = dependency_closure(cards, chosen, overlay.alias, cats, include_deps)
        external.discard(alias)

        staged_paths = ws.staging.entries()
        staged = sorted(p for p in included if p in staged_paths)
        conflicts = [{"address": format_address(overlay.alias, p), "reason": "staged change pending (apply or discard it first)",
                      "fix": f"`mindslice apply {p}` to accept the staged change, or `mindslice discard {p}` to drop it"}
                     for p in staged]
        for path in sorted(included):
            parsed = cards[path][1]
            if path in slice_paths and any(targets_slice(r) == path for r in parsed.extends):
                conflicts.append({"address": format_address(overlay.alias, path),
                                  "reason": f"extends {format_address(alias, path)} at the same path; merge the two "
                                            "into one card first",
                                  "fix": "rewrite the overlay card with the combined text and drop its `extends` link, "
                                         "so one card replaces the slice's"})
        if conflicts:
            raise BakeConflictError(f"bake into {alias} stopped before writing: {len(conflicts)} card(s) can't move as they are",
                                    conflicts=conflicts,
                                    next_steps=[f"{c['address']}: {c['fix']}" for c in conflicts]
                                    + [f"Then run the same `mindslice bake {alias}` command again; "
                                       "`--dry-run` previews it without writing."])

        def mapper(raw: str) -> str:
            res = resolve_ref(raw, overlay.alias, cats)
            if res.resolved and res.path and (res.mount == alias or (res.mount == overlay.alias and res.path in included)):
                return res.path
            if res.resolved and res.mount and res.path:
                return format_address(res.mount, res.path)
            return raw

        files: dict[str, str] = {}
        created: list[str] = []
        replaced: list[str] = []
        for path in sorted(included):
            text, parsed = cards[path]
            new_text = rewrite_refs(text, parsed, mapper) if mount else export_text(text, parsed, overlay.alias, cats)
            new_parsed = parse_card(new_text)
            if path in new_parsed.supersedes:  # it replaces the file it superseded; a self-reference would be a cycle
                fields = dict(new_parsed.frontmatter)
                fields["supersedes"] = [r for r in new_parsed.supersedes if r != path]
                new_text = reassemble(new_parsed, new_text, fields, None)
            files[path] = normalize_newlines(new_text)
            (replaced if path in slice_paths else created).append(format_address(alias, path))

        sm = load_slice_manifest(mount.root) if mount else SliceManifest(
            name=alias.lstrip("@"), version="0.1.0", alias=alias,
            description=f"Baked from {overlay.alias} (prefix={prefix})", present=True)
        declared = set()
        for dep in sm.dependencies:
            try:
                declared.add(normalize_alias(dep))
            except InvalidAddressError:
                pass
        added_deps = sorted(external - declared)
        requested = default_output(ws, alias, mount) if output_path is None else Path(output_path).expanduser().absolute()
        requested = Path(os.path.abspath(requested))
        fmt = archive_format(requested)
        output = requested if fmt == "directory" else default_output(ws, alias, mount)
        if fmt != "directory" and output in requested.parents:
            raise MountError("the archive cannot go inside the slice directory being created", output=str(requested))
        if fmt != "directory" and requested.exists():
            raise AlreadyExistsError(f"{requested} already exists", path=str(requested))
        if mount and (output == mount.root or mount.root in output.parents):
            raise MountError(f"the new slice can't go inside {alias}'s own folder ({mount.root}); pass another output",
                             alias=alias, output=str(output))
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise AlreadyExistsError(f"{output} already exists and is not empty", path=str(output))
        for destination in {output, requested}:
            resolved = destination.resolve()
            for root in (ws.staging.root, ws.cache_dir, ws.history.root):
                if resolved == root.resolve() or root.resolve() in resolved.parents:
                    raise MountError("cannot bake into MindSlice internal directories", output=str(destination))
            for existing in table.all():
                if resolved == existing.root.resolve() or existing.root.resolve() in resolved.parents:
                    raise MountError(f"cannot bake inside mounted {existing.alias}'s folder", output=str(destination))
        new_version = version if version is not None else (bump_version(sm.version) if mount else sm.version)
        if name is not None:
            sm.name = name
        elif not sm.present:
            sm.name = mount.root.name.removesuffix(".slice")
        if description is not None or mount is None:
            sm.description, _ = truncate(" ".join((description if description is not None else sm.description).split()),
                                         DESCRIPTION_CHARS)
        result: dict[str, Any] = {
            "alias": alias,
            "output": str(requested),
            "path": str(output),
            "previous_path": str(mount.root) if mount else None,
            "format": fmt,
            "name": sm.name,
            "cards": sorted(included),
            "dependencies": sorted(declared | external),
            "dry_run": dry_run,
            "created": created,
            "replaced": replaced,
            "included_dependencies": pulled,
            "dependencies_added": added_deps,
            "warnings": warnings,
        }
        if new_version:
            result["version"] = new_version
        if dry_run:
            return result

        output.parent.mkdir(parents=True, exist_ok=True)
        tmp_root = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
        try:
            tree = tmp_root / output.name
            if mount:
                shutil.copytree(mount.root, tree, symlinks=False, ignore=shutil.ignore_patterns(".git", ".history", ".bake-plan.json"))
            else:
                tree.mkdir()
            for path, text in files.items():
                dest = tree / f"{path}.md"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(text.encode("utf-8"))
            sm.alias = alias
            sm.dependencies = list(sm.dependencies) + added_deps
            sm.version = new_version
            (tree / SLICE_FILE).write_bytes(dump_slice_manifest(sm).encode("utf-8"))
            if fmt != "directory":
                write_archive(tree, requested, fmt)
            if output.exists():
                output.rmdir()  # an empty directory (checked above)
            os.replace(tree, output)
            fsync_dir(output.parent)
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
        validation = validate_slice_dir(output, ws)

        # The new folder takes over the mount: same alias, precedence and role; the old folder is untouched.
        new_mount = Mount(alias, portable_path(ws.root, output), mount.precedence if mount else 50,
                          mount.role if mount else "baseline", "slice", output)
        mounts = [new_mount if m.alias == alias else m for m in table.mounts] if mount else [*table.mounts, new_mount]
        actions = [file_action(ws.root / MOUNTS_FILE, dump_mounts(MountTable(overlay, mounts)))]
        events = []
        retired = retire_overlay_paths(ws, table, alias, sorted(included), [], cats, actions=actions, events=events)
        active = ws.history.applied()
        baked_cards = []
        for path in sorted(included):
            source = format_address(overlay.alias, path)
            before = file_sha(overlay.root / f"{path}.md")
            tip, ids = active.get(source, (None, []))
            baked_cards.append({"source": source, "target": format_address(alias, path),
                                "before_sha256": before, "after_sha256": file_sha(output / f"{path}.md"),
                                "change_ids": ids if tip == before else []})
        baked = event("baked", alias=alias, path=str(output), output=str(requested),
                      previous_path=str(mount.root) if mount else None, version=new_version, cards=baked_cards,
                      change_ids=list(dict.fromkeys(id for card in baked_cards for id in card["change_ids"])),
                      retired_overlay_cards=retired.get("retired_overlay_cards", []))
        events.append(baked)
        guards = [{"path": str(p), "sha256": file_sha(p)} for p in sorted(output.rglob("*")) if p.is_file()]
        ws.history.transact(actions, events, guards=guards)
        table = ws._reload_table()
        ws._sync(table)
        result.update(retired)
        result["history_event_id"] = baked["event_id"]
        result["validation"] = {"ok": validation["ok"], "errors": validation["errors"],
                                "warnings": len(validation["warnings"])}
        return result


__all__ = ["bake"]
