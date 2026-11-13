"""Workspace bake planning and execution. Review never holds a lock while waiting for a user.

A plan fingerprints its inputs; execution rebuilds and validates it under LOCK_EX. All outputs
are prepared before a single recoverable mount/overlay/history transaction is started.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from ..model.addressing import MountCatalog, format_address, normalize_alias, resolve_ref
from .bake import bump_version, default_output
from ..model.card import normalize_newlines, parse_card, sha256_bytes
from ..storage.config import MOUNTS_FILE, SLICE_FILE, Mount, MountTable, SliceManifest, dump_mounts, dump_slice_manifest, load_slice_manifest, portable_path
from ..errors import BakeConflictError, InvalidArgumentsError
from ..storage.fsutil import atomic_write_text, fsync_dir, fsync_file, iter_markdown
from ..storage.history import change, event, file_action, file_sha
from ..model.lineage import strongly_connected_cycles
from .slice_transfer import overlay_cards, rewrite_refs
from ..operations.staging import _diff_overlay, _diff_staging
from ..storage.card_io import read_card_file
from ..model.card import reassemble

if TYPE_CHECKING:
    from ..workspace import Workspace

PLAN_FILE = ".bake-plan.json"
MERGE_FIX = ("merge the two into one card: rewrite the overlay card with the combined text and drop its "
             "`extends` link")


def _stale(message: str, **details) -> BakeConflictError:
    """A plan no longer matches the workspace: nothing to fix, only to plan again."""
    return BakeConflictError(message, code="stale_bake_plan", next_steps=[
        "Run `mindslice bake` again: the plan is rebuilt from the current workspace, and destination "
        "choices saved for unchanged cards are kept."], **details)


def _selectors(plan: dict, ids: list[str]) -> list[str]:
    """Shortest ``--assign``/``--defer`` selectors for ``ids``: a whole top folder when every card in it is listed."""
    wanted, out = set(ids), []
    for path in ids:
        folder = path.partition("/")[0] + "/" if "/" in path else None
        inside = [c["id"] for c in plan["cards"] if folder and c["id"].startswith(folder)]
        selector = folder if folder and set(inside) <= wanted else path
        if selector not in out:
            out.append(selector)
    return out


def blocked_message(plan: dict) -> str:
    parts = []
    if plan["unassigned"]:
        parts.append(f"{len(plan['unassigned'])} overlay card(s) need a destination")
    if plan["blockers"]:
        parts.append(f"{len(plan['blockers'])} blocker(s) must be resolved")
    return "bake stopped before writing: " + " and ".join(parts or ["the plan is not ready"])


def next_steps(plan: dict) -> list[str]:
    """What the user has to do before this plan can bake; empty when it is ready."""
    steps = []
    if plan["unassigned"]:
        selectors = _selectors(plan, plan["unassigned"])
        shown = ", ".join(selectors[:5]) + (f" (+{len(selectors) - 5} more)" if len(selectors) > 5 else "")
        assign = " ".join(f"--assign '{sel}=@ALIAS'" for sel in selectors[:3])
        steps.append(f"Choose a destination for {shown}: `mindslice bake {assign}` sends cards to a new or mounted "
                     f"slice; use `--defer '{selectors[0]}'` instead to leave cards in overlay; "
                     "or run `mindslice bake` in a terminal to decide card by card.")
    seen = set()
    for item in plan["blockers"]:
        if item.get("derived"):  # disappears with the blocker it follows from
            continue
        where = item.get("address") or item.get("alias") or "workspace"
        key = (where, item.get("ref")) if item.get("ref") else (where, item["reason"])
        if key in seen:  # one broken reference can surface as two blockers; its first fix covers both
            continue
        seen.add(key)
        steps.append(f"{where}: {item.get('fix') or item['reason']}")
    return steps


def _tree_files(root: Path):
    """Match the baseline tree copied to a batch output, excluding workspace machinery."""
    if not root.is_dir():
        return
    for current, dirs, files in os.walk(root, followlinks=True):
        # Symlink loops are rejected rather than making a review hang.
        for name in list(dirs):
            p = Path(current) / name
            if name in (".git", ".history", ".cache"):
                dirs.remove(name)
            elif p.is_symlink() and p.resolve() in {Path(current).resolve(), *(a.resolve() for a in Path(current).parents)}:
                raise InvalidArgumentsError("directory symlink cycle in bake source", path=str(p))
        for name in sorted(files):
            if name == PLAN_FILE:
                continue
            yield Path(current) / name


def _revision(ws, table):
    rows = [(str(ws.root / MOUNTS_FILE), file_sha(ws.root / MOUNTS_FILE))]
    for mount in table.all():
        rows.append((str(mount.root), mount.root.is_dir()))
        for p in _tree_files(mount.root):
            rows.append((str(p), file_sha(p)))
    for p in _tree_files(ws.staging.root):
        rows.append((str(p), file_sha(p)))
    return sha256_bytes(json.dumps(sorted(rows), ensure_ascii=False).encode())


def _refs(parsed):
    return [(k, r) for k in ("extends", "supersedes") for r in parsed.list_field(k)] + [
        ("wikilink", r) for r in parsed.wikilink_targets()]


def load_plan(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise InvalidArgumentsError(f"cannot read bake plan: {path}: {exc}") from exc
    valid = isinstance(value, dict) and value.get("schema_version") == 1
    valid = valid and isinstance(value.get("assignments"), dict) and isinstance(value.get("cards"), list)
    valid = valid and isinstance(value.get("slices"), list) and isinstance(value.get("workspace"), str)
    valid = valid and isinstance(value.get("revision"), str)
    if valid:
        valid = all(isinstance(c, dict) and isinstance(c.get("id"), str) and isinstance(c.get("sha256"), str)
                    for c in value["cards"])
        valid = valid and all(isinstance(p, str) and (a is None or isinstance(a, str))
                              for p, a in value["assignments"].items())
    if not valid:
        raise InvalidArgumentsError("invalid bake plan; regenerate with bake --dry-run --json", path=str(path))
    return value


def save_plan(ws, plan):
    with ws._writing() as table:
        if plan.get("revision") != _revision(ws, table):
            raise _stale("workspace changed during review; run bake again")
        atomic_write_text(ws.root / PLAN_FILE, json.dumps(plan, ensure_ascii=False, indent=2) + "\n")


def plan_bake(ws: "Workspace", assignments: dict[str, str | None] | None = None, *, resume: bool = True) -> dict:
    with ws._writing() as table:
        ws._sync(table, verify=True)
        choices = {}
        saved = ws.root / PLAN_FILE
        if resume and saved.exists():
            old = load_plan(saved)
            if old.get("workspace") != str(ws.root):
                raise InvalidArgumentsError("saved bake plan belongs to another workspace")
            old_hashes = {c["id"]: c["sha256"] for c in old.get("cards", [])}
            live_paths = overlay_cards(ws, table)
            for path, dest in old["assignments"].items():
                # Choices survive baseline fixes, but changed/recreated cards need a new review.
                if path in live_paths and path in old_hashes and old_hashes[path] == file_sha(table.overlay.root / f"{path}.md"):
                    choices[path] = dest
        choices.update(assignments or {})
        return _prepare(ws, table, choices)[0]


def _prepare(ws, table, assignments):
    revision = _revision(ws, table)
    cards = overlay_cards(ws, table)
    if not isinstance(assignments, dict) or any(not isinstance(p, str) or p not in cards for p in assignments):
        raise InvalidArgumentsError("bake assignments must use existing overlay card IDs")
    choices = {}
    for path, alias in assignments.items():
        if alias is not None and not isinstance(alias, str):
            raise InvalidArgumentsError("a bake destination must be an alias or null (defer)", id=path)
        dest = normalize_alias(alias) if alias is not None else None
        if dest == table.overlay.alias:
            raise InvalidArgumentsError("overlay is not a bake destination", id=path)
        choices[path] = dest
    cats = ws.index.catalogs()
    pending = _diff_staging(ws, table)["items"]
    staged = {i["id"] for i in pending}
    diff = {i["id"]: i for i in _diff_overlay(ws, table)["items"]}
    items, blockers = [], []
    for path, (text, parsed) in sorted(cards.items()):
        candidates = set()
        for m in table.mounts:
            if path in cats[m.alias].paths:
                candidates.add(m.alias)
        for raw in parsed.extends + parsed.supersedes:
            ref = resolve_ref(raw, table.overlay.alias, cats)
            if ref.resolved and ref.mount != table.overlay.alias:
                candidates.add(ref.mount)
        if path not in choices:
            if path in staged:
                choices[path] = None
            elif len(candidates) == 1:
                choices[path] = next(iter(candidates))
        item = dict(diff.get(path, {}), id=path, address=format_address(table.overlay.alias, path),
                    sha256=file_sha(table.overlay.root / f"{path}.md"), summary=parsed.index_parts()[0],
                    candidates=sorted(candidates), destination=choices.get(path),
                    state="unassigned" if path not in choices else ("assigned" if choices[path] else "deferred"))
        items.append(item)
        if choices.get(path) and path in staged:
            blockers.append({"address": item["address"], "reason": "staged change pending; apply, discard or defer this card",
                             "fix": f"`mindslice apply {path}` to accept the staged change or `mindslice discard {path}` "
                                    f"to drop it, or keep the card in overlay with `--defer {path}`"})
    destinations = {p: a for p, a in choices.items() if a}
    groups = defaultdict(list)
    for path, alias in sorted(destinations.items()):
        groups[alias].append(path)

    # Original resolution for overlay references; future catalogs also permit explicit references
    # to a new slice whose cards are assigned by this very plan.
    future = copy.deepcopy(cats)
    for path, alias in destinations.items():
        future.setdefault(alias, MountCatalog()).add(path, cards[path][1].aliases)

    def resolve(raw, source):
        result = resolve_ref(raw, source, cats)
        return result if result.resolved else resolve_ref(raw, source, future)

    def rewrite(text, parsed, source, target, path, *, portable=True):
        def mapper(raw):
            ref = resolve(raw, source)
            if not ref.resolved:
                if portable:
                    blockers.append({"address": format_address(target, path), "ref": raw, "reason": "unresolved reference",
                                     "fix": f"the card references {raw!r}, which no mounted card matches: correct or "
                                            "remove that reference"
                                            + (f", or keep the card in overlay with `--defer {path}`"
                                               if source == table.overlay.alias else "")})
                return raw
            alias, dest_path = ref.mount, ref.path
            if alias == table.overlay.alias:
                alias = destinations.get(dest_path)
                if alias is None:
                    if portable:
                        needed = format_address(table.overlay.alias, dest_path)
                        blockers.append({"address": format_address(target, path), "ref": raw,
                                         "reason": "referenced overlay card needs a destination",
                                         "fix": f"it references {needed}, which stays in overlay: bake that card too "
                                                f"with `--assign '{dest_path}={target}'`"
                                                + (f", or keep this card in overlay with `--defer {path}`"
                                                   if source == table.overlay.alias else "")})
                    return raw
            if not portable and ref.mount != table.overlay.alias:
                return raw
            return dest_path if alias == target else format_address(alias, dest_path)
        result = rewrite_refs(text, parsed, mapper)
        return normalize_newlines(result)

    # Keep overlay copies required by pending work or unchanged read-only mounts. Otherwise all
    # retiring targets are mapped together, so a deferred referrer is rewritten only once.
    retained = {}
    def protect(parsed, source, cause):
        for _, raw in _refs(parsed):
            ref = resolve(raw, source)
            if ref.resolved and ref.mount == table.overlay.alias and ref.path in destinations:
                retained.setdefault(ref.path, cause)
    for item in pending:
        path = item["id"]
        if path in cards:
            protect(cards[path][1], table.overlay.alias, "referenced by pending overlay card")
        text, _ = read_card_file(ws.staging.file(path))
        if text is not None:
            protect(parse_card(text), table.overlay.alias, "referenced by staged content")
    for m in table.mounts:
        if m.alias not in groups:
            for path, _ in iter_markdown(m.root, exclude=tuple(ws._exclude())):
                text, _ = read_card_file(m.root / f"{path}.md")
                if text is not None:
                    protect(parse_card(text), m.alias, f"referenced by read-only {m.alias}")
    last = -1
    while last != len(retained):
        last = len(retained)
        for path in list(retained):
            protect(cards[path][1], table.overlay.alias, "required by retained overlay copy")

    prepared, slices, used_outputs = {}, [], set()
    projected = {}
    same_path = {}  # baked address -> the overlay card that extends it at its own path
    for alias, paths in sorted(groups.items()):
        mount = table.get(alias)
        files = {}
        baseline_rebased = []
        if mount:
            if not mount.root.is_dir():
                blockers.append({"alias": alias, "reason": "mounted directory is missing",
                                 "fix": f"restore {mount.root}, or `mindslice unmount {alias}` and assign its cards "
                                        "elsewhere (`mindslice doctor` lists missing directories)"})
            for path, _ in iter_markdown(mount.root, exclude=tuple(ws._exclude())):
                text, _ = read_card_file(mount.root / f"{path}.md")
                if text is not None and path not in paths:
                    files[path] = rewrite(text, parse_card(text), alias, alias, path)
                    if files[path] != normalize_newlines(text):
                        baseline_rebased.append(format_address(alias, path))
        for path in paths:
            text, parsed = cards[path]
            for raw in parsed.extends:
                ref = resolve(raw, table.overlay.alias)
                if ref.resolved and ref.mount == alias and ref.path == path:
                    same_path[format_address(alias, path)] = format_address(table.overlay.alias, path)
                    blockers.append({"address": format_address(table.overlay.alias, path),
                                     "reason": "extends destination at the same path; consolidate content first",
                                     "fix": f"{MERGE_FIX}, or keep the card in overlay with `--defer {path}`"})
            value = rewrite(text, parsed, table.overlay.alias, alias, path)
            parsed_new = parse_card(value)
            if path in parsed_new.supersedes:
                fields = dict(parsed_new.frontmatter, supersedes=[r for r in parsed_new.supersedes if r != path])
                value = reassemble(parsed_new, value, fields, None)
            files[path] = value
        sm = load_slice_manifest(mount.root) if mount else SliceManifest(
            name=alias[1:], version="0.1.0", alias=alias, description=f"Baked from {table.overlay.alias}", present=True)
        if sm.errors:
            blockers.append({"alias": alias, "reason": "invalid slice manifest", "errors": sm.errors,
                             "fix": f"correct {mount.root / SLICE_FILE} (`mindslice validate {mount.root}` lists the problems)"})
        sm.alias = alias
        sm.name = sm.name or (mount.root.name.removesuffix(".slice") if mount else alias[1:])
        sm.version = bump_version(sm.version) if mount and sm.version else (sm.version or "0.1.0")
        declared = set()
        for dep in sm.dependencies:
            try:
                declared.add(normalize_alias(dep))
            except ValueError:
                blockers.append({"alias": alias, "dependency": dep, "reason": "invalid dependency alias",
                                 "fix": f"correct the dependency {dep!r} in {mount.root / SLICE_FILE if mount else SLICE_FILE}"})
        dependencies = set(declared)
        for path, value in files.items():
            parsed = parse_card(value)
            projected[(alias, path)] = parsed
            if parsed.errors:
                blockers.append({"address": format_address(alias, path), "reason": "invalid card", "errors": parsed.errors,
                                 "fix": "correct the card's frontmatter so it parses"
                                        + (f", or keep it in overlay with `--defer {path}`" if path in paths else "")})
            for _, raw in _refs(parsed):
                ref = resolve_ref(raw, alias, future)
                if ref.mount and ref.mount != alias:
                    dependencies.add(ref.mount)
        dependencies.discard(alias)
        sm.dependencies = sorted(dependencies)
        for dep in sm.dependencies:
            if dep not in future or dep == table.overlay.alias:
                blockers.append({"alias": alias, "dependency": dep, "reason": "missing or nonportable dependency",
                                 "fix": (f"cards bound for {alias} reference overlay cards that stay behind: give those "
                                         "cards a destination too" if dep == table.overlay.alias else
                                         f"mount the slice it depends on (`mindslice mount PATH --alias {dep}`), or "
                                         f"drop {dep} from the slice's declared dependencies and card references")})
        output = default_output(ws, alias, mount)
        # Two mounts can have the same directory basename; reserve outputs across the full batch.
        while str(output) in used_outputs:
            output = output.with_name(output.stem + "-2.slice")
        used_outputs.add(str(output))
        for root in [ws.staging.root, ws.cache_dir, ws.history.root] + [m.root for m in table.all()]:
            if output.resolve() == root.resolve() or root.resolve() in output.resolve().parents:
                blockers.append({"alias": alias, "reason": "output falls inside a mounted/internal directory", "path": str(output),
                                 "fix": f"bake this slice on its own to another location: `mindslice bake {alias} --output DIR`"
                                        + ("" if mount else " (with `--prefix` to select its cards)")})
        slices.append({"alias": alias, "path": str(output), "output": str(output),
                       "previous_path": str(mount.root) if mount else None, "version": sm.version,
                       "action": "update" if mount else "create", "cards": paths,
                       "rebased_baseline_cards": sorted(baseline_rebased),
                       "dependencies": sm.dependencies, "dependencies_added": sorted(dependencies - declared)})
        prepared[alias] = (files, sm, output, mount)

    # Validate the full future lineage, including unchanged mounts. Detect cycles introduced by
    # assigning different overlay cards to the same baseline namespace.
    graph = defaultdict(list)
    for row in ws.index.all_cards():
        key = (row["mount"], row["path"])
        if row["mount"] in groups or (row["mount"] == table.overlay.alias and row["path"] in destinations and row["path"] not in retained):
            continue
        mount = table.get(row["mount"])
        text, _ = read_card_file(mount.root / f"{row['path']}.md")
        if text is not None:
            projected[key] = parse_card(text)
    for (alias, path), parsed in projected.items():
        for kind, raw in _refs(parsed):
            ref = resolve_ref(raw, alias, future)
            if alias in groups and not ref.resolved:
                blockers.append({"address": format_address(alias, path), "ref": raw, "reason": "unresolved output reference",
                                 "fix": f"the baked card would reference {raw!r}, which nothing in the planned workspace "
                                        "matches: correct or remove that reference, or bake its target in the same run"})
            if kind != "wikilink" and ref.resolved:
                graph[format_address(alias, path)].append(ref.address)
    nodes = set(graph) | {n for values in graph.values() for n in values}
    for cycle in strongly_connected_cycles(sorted(nodes), lambda n: graph.get(n, ())):
        cause = same_path.get(cycle[0]) if len(cycle) == 1 else None
        blockers.append({"reason": "lineage cycle in planned workspace", "cards": cycle} | (
            # Baked as it is, a card extending its own path would extend itself: one problem, not two.
            {"fix": f"follows from {cause} extending this path; resolving that card removes the cycle", "derived": True}
            if cause else
            {"fix": "remove one `extends`/`supersedes` link among " + ", ".join(cycle) + " to break the cycle"}))

    # Retained and staged cards stay byte-identical. All other remaining overlay refs are rebased
    # in one pass, using only targets that really retire.
    retired = set(destinations) - set(retained)
    rebased = {}
    for path, (text, parsed) in cards.items():
        if path in destinations or path in staged:
            continue
        def mapper(raw):
            ref = resolve(raw, table.overlay.alias)
            if ref.resolved and ref.mount == table.overlay.alias and ref.path in retired:
                return format_address(destinations[ref.path], ref.path)
            return raw
        value = rewrite_refs(text, parsed, mapper)
        if value != text:
            rebased[path] = value
    plan = {"schema_version": 1, "workspace": str(ws.root), "revision": revision,
            "assignments": choices, "cards": items, "slices": slices,
            "unassigned": [i["id"] for i in items if i["state"] == "unassigned"],
            "deferred": [p for p, a in choices.items() if a is None],
            "pending_review": pending, "retained_overlay_cards": [
                {"address": format_address(table.overlay.alias, p), "reason": retained[p]} for p in sorted(retained)],
            "rebased_references": sorted(rebased), "blockers": blockers,
            "remaining_overlay_cards": sorted(set(cards) - retired)}
    plan["ready"] = not (plan["unassigned"] or blockers)
    if revision != _revision(ws, table):
        raise _stale("files changed during planning; retry review")
    return plan, prepared, retired, rebased


def _reviewed(ws, table, reviewed):
    if not isinstance(reviewed, dict) or reviewed.get("schema_version") != 1 or reviewed.get("workspace") != str(ws.root):
        raise InvalidArgumentsError("invalid bake plan or wrong workspace")
    if reviewed.get("revision") != _revision(ws, table):
        raise _stale("workspace changed since review; run bake again")
    ws._sync(table, verify=True)
    prepared = _prepare(ws, table, reviewed.get("assignments"))
    if prepared[0]["slices"] != reviewed.get("slices"):
        raise _stale("bake outputs changed since review; run bake again")
    return prepared


def inspect_plan(ws: "Workspace", reviewed: dict) -> dict:
    with ws._writing() as table:
        return _reviewed(ws, table, reviewed)[0]


def execute(ws: "Workspace", reviewed: dict) -> dict:
    with ws._writing() as table:
        plan, prepared, retired, rebased = _reviewed(ws, table, reviewed)
        if not plan["ready"]:
            raise BakeConflictError(blocked_message(plan), plan=plan, next_steps=next_steps(plan) + [
                "Then plan and bake again."])
        if not prepared:
            return {"baked": [], "remaining_overlay_cards": plan["remaining_overlay_cards"],
                    "retained_overlay_cards": [], "pending_review": len(plan["pending_review"]),
                    "rebased_references": [], "dry_run": False}
        ws.history.events()  # fail before producing outputs if the log is corrupt
        temporary = Path(tempfile.mkdtemp(prefix="mindslice-batch-"))
        published = []
        transaction_started = False
        try:
            # Preparation is isolated. No mount, overlay or final output changes until all trees exist.
            for alias, (files, sm, output, mount) in prepared.items():
                tree = temporary / alias[1:]
                tree.mkdir()
                if mount:
                    for source in _tree_files(mount.root):
                        dest = tree / source.relative_to(mount.root)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, dest)
                for path, text in files.items():
                    atomic_write_text(tree / f"{path}.md", text)
                atomic_write_text(tree / SLICE_FILE, dump_slice_manifest(sm))
            if plan["revision"] != _revision(ws, table):
                raise _stale("files changed while preparing bake; review again")
            # Publish via a sibling temp directory so the final rename works across devices.
            for alias, (_, _, output, _) in prepared.items():
                if output.exists():
                    raise BakeConflictError("output appeared during bake", path=str(output), next_steps=[
                        "Run `mindslice bake` again: planning picks an output directory that is still free."])
                output.parent.mkdir(parents=True, exist_ok=True)
                sibling = Path(tempfile.mkdtemp(prefix=".bake-", dir=output.parent))
                try:
                    shutil.copytree(temporary / alias[1:], sibling / "tree")
                    for p in _tree_files(sibling / "tree"):
                        fsync_file(p)
                    for directory, _, _ in os.walk(sibling / "tree", topdown=False):
                        fsync_dir(Path(directory))
                    os.rename(sibling / "tree", output)
                    published.append(output)
                    fsync_dir(output.parent)
                finally:
                    shutil.rmtree(sibling, ignore_errors=True)
            new_mounts = {a: Mount(a, portable_path(ws.root, output), m.precedence if m else 50,
                                   m.role if m else "baseline", "slice", output)
                          for a, (_, _, output, m) in prepared.items()}
            mounts = [new_mounts.pop(m.alias, m) for m in table.mounts] + list(new_mounts.values())
            actions = [file_action(ws.root / MOUNTS_FILE, dump_mounts(MountTable(table.overlay, mounts)))]
            events = []
            for path, text in rebased.items():
                action = file_action(table.overlay.root / f"{path}.md", text)
                actions.append(action)
                events.append(change("applied", address=format_address(table.overlay.alias, path), op="rebase", origin="engine",
                                     reason="Rebase references after workspace bake", before_sha256=action["before_sha256"],
                                     after_sha256=action["after_sha256"]))
            actions += [file_action(table.overlay.root / f"{p}.md", None, table.overlay.root) for p in sorted(retired)]
            if (ws.root / PLAN_FILE).exists():
                actions.append(file_action(ws.root / PLAN_FILE, None))
            active = ws.history.applied()
            receipt = []
            for result in plan["slices"]:
                baked_cards = []
                for path in result["cards"]:
                    address = format_address(table.overlay.alias, path)
                    before = file_sha(table.overlay.root / f"{path}.md")
                    tip, ids = active.get(address, (None, []))
                    baked_cards.append({"source": address, "target": format_address(result["alias"], path),
                                        "before_sha256": before, "after_sha256": file_sha(Path(result["path"]) / f"{path}.md"),
                                        "change_ids": ids if tip == before else []})
                record = event("baked", alias=result["alias"], path=result["path"], output=result["output"],
                               previous_path=result["previous_path"], version=result["version"], cards=baked_cards,
                               change_ids=list(dict.fromkeys(id for c in baked_cards for id in c["change_ids"])),
                               retired_overlay_cards=[format_address(table.overlay.alias, p) for p in result["cards"] if p in retired])
                events.append(record)
                receipt.append(dict(result, history_event_id=record["event_id"]))
            guards = [{"path": str(p), "sha256": file_sha(p)} for output in published for p in _tree_files(output)]
            if plan["revision"] != _revision(ws, table):
                raise _stale("files changed before commit; review again")
            transaction_started = True
            ws.history.transact(actions, events, guards=guards)
            ws._sync(ws._reload_table())
            return {"baked": receipt, "remaining_overlay_cards": plan["remaining_overlay_cards"],
                    "retained_overlay_cards": plan["retained_overlay_cards"], "pending_review": len(plan["pending_review"]),
                    "rebased_references": plan["rebased_references"], "dry_run": False}
        except BaseException:
            # Once journaled, recovery owns the outputs. Never remove files a pending commit needs.
            if not transaction_started:
                for output in published:
                    shutil.rmtree(output)
            raise
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
