"""Transactional sandbox: ``staging/`` buffer, ``diff()``, journaled ``apply()`` and ``discard()``.

``staging/<id>.md`` is the complete prospective content of ``overlay/<id>.md``.
``staging/.manifest.json`` records, per id, the ``base_sha256`` of the overlay
file when it was first staged (``null`` = "must still be absent") and
deletion tombstones. ``staging/.apply_journal.json`` exists only while an
``apply()`` batch is in flight and is removed strictly last, so any process
that finds it can finish the batch idempotently.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..model.addressing import format_address, parse_address, resolve_ref
from ..model.card import ParsedCard, parse_card
from ..errors import ApplyConflictError, InvalidArgumentsError, LineageCycleError
from ..storage.fsutil import atomic_write_text, durable_move, fsync_dir, iter_markdown, prune_empty_dirs, unlink_if_exists
from ..storage.history import change, file_action, transitions
from .writer import check_cycles, prospective_successors
from .impact import inbound_impact, supersede_targets
from ..storage.card_io import read_card_file

if TYPE_CHECKING:  # pragma: no cover
    from ..storage.config import MountTable
    from ..workspace import Workspace

MANIFEST_FILE = ".manifest.json"
JOURNAL_FILE = ".apply_journal.json"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _short(sha: str | None) -> str:
    return sha[:12] if sha else "absent"


def precondition_conflict(base: str | None, current: str | None) -> str | None:
    if base == current:
        return None
    if base is None:
        return f"expected absent, found {_short(current)}"
    if current is None:
        return f"expected {_short(base)}, found absent"
    return f"expected {_short(base)}, found {_short(current)}"


def unified(before: str | None, after: str | None, before_label: str, after_label: str) -> str:
    a = (before or "").splitlines(keepends=True)
    b = (after or "").splitlines(keepends=True)
    lines = difflib.unified_diff(
        a, b, fromfile=before_label if before is not None else "/dev/null",
        tofile=after_label if after is not None else "/dev/null",
    )
    out = []
    for line in lines:
        out.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    return "".join(out)


class StagingArea:
    def __init__(self, root: Path) -> None:
        self.root = root

    # -- files -----------------------------------------------------------
    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST_FILE

    @property
    def journal_path(self) -> Path:
        return self.root / JOURNAL_FILE

    def file(self, path: str) -> Path:
        return self.root / f"{path}.md"

    def has_journal(self) -> bool:
        return self.journal_path.exists()

    def load_manifest(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        entries = data.get("entries", {}) if isinstance(data, dict) else {}
        return {k: dict(v) for k, v in entries.items() if isinstance(v, dict)}

    def manifest_text(self, entries: dict[str, dict[str, Any]]) -> str | None:
        if not entries:
            return None
        payload = {"version": 1, "entries": dict(sorted(entries.items()))}
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    def save_manifest(self, entries: dict[str, dict[str, Any]]) -> None:
        if not entries:
            unlink_if_exists(self.manifest_path)
            return
        atomic_write_text(self.manifest_path, self.manifest_text(entries))

    def staged_files(self) -> dict[str, Path]:
        return {rel: self.file(rel) for rel, _ in iter_markdown(self.root)}

    def entries(self) -> dict[str, dict[str, Any]]:
        """Manifest entries plus orphan staged files (treated as creates that require absence)."""
        out = self.load_manifest()
        for path in self.staged_files():
            if path not in out:
                out[path] = {"op": "write", "base_sha256": None, "history": [], "orphan": True}
        return dict(sorted(out.items()))

    # -- prospective state ----------------------------------------------
    def prospective_state(self, path: str, overlay_root: Path) -> tuple[str | None, str | None]:
        entry = self.load_manifest().get(path)
        if entry is not None and entry.get("op") == "delete":
            return None, None
        staged = read_card_file(self.file(path))
        if staged[0] is not None:
            return staged
        return read_card_file(overlay_root / f"{path}.md")

    def prospective_overrides(self, overlay_root: Path) -> dict[str, ParsedCard | None]:
        overrides: dict[str, ParsedCard | None] = {}
        for path, entry in self.entries().items():
            if entry.get("op") == "delete":
                overrides[path] = None
                continue
            text, _ = read_card_file(self.file(path))
            if text is not None:
                overrides[path] = parse_card(text)
        return overrides

    # -- staged mutations -------------------------------------------------
    def _mutate(self, path, manifest, text, audit=None, events=None):
        if audit is None:
            self.save_manifest(manifest)
            if text is None:
                self._drop_file(self.file(path))
            else:
                atomic_write_text(self.file(path), text)
        else:
            audit.transact([file_action(self.manifest_path, self.manifest_text(manifest)),
                            file_action(self.file(path), text, self.root)], events or [])

    def stage_write(self, path: str, text: str, overlay_root: Path, op: str, requires_approval: str | None = None,
                    *, audit=None, event=None) -> None:
        manifest = self.load_manifest()
        entry = manifest.get(path)
        if entry is None:
            _, base = read_card_file(overlay_root / f"{path}.md")
            entry = {"op": "write", "base_sha256": base, "history": []}
        entry["op"] = "write"
        entry["history"] = list(entry.get("history") or []) + [op]
        entry["updated_at"] = _now()
        if requires_approval:
            entry["requires_approval"] = requires_approval
        if event:
            entry["change_ids"] = list(entry.get("change_ids", [])) + [event["change_id"]]
        manifest[path] = entry
        self._mutate(path, manifest, text, audit, [event] if event else [])

    def stage_delete(self, path: str, overlay_root: Path, requires_approval: str | None = None,
                     *, audit=None, event=None) -> bool:
        manifest = self.load_manifest()
        entry = manifest.get(path)
        if entry is None:
            _, base = read_card_file(overlay_root / f"{path}.md")
            entry = {"op": "write", "base_sha256": base, "history": []}
        events = [event] if event else []
        ids = list(entry.get("change_ids", []))
        if event:
            ids.append(event["change_id"])
        if entry.get("base_sha256") is None:
            # Cancel the entire proposed revision chain, including this delete request.
            manifest.pop(path, None)
            events += transitions("discarded", ids, cause="staged_create_deleted")
        else:
            if entry.get("op") == "delete":
                return self._drop_file(self.file(path))
            entry["op"] = "delete"
            entry["history"] = list(entry.get("history") or []) + ["delete"]
            entry["updated_at"] = _now()
            if requires_approval:
                entry["requires_approval"] = requires_approval
            if ids:
                entry["change_ids"] = ids
            manifest[path] = entry
        self._mutate(path, manifest, None, audit, events)
        return True

    def _drop_file(self, file: Path) -> bool:
        removed = unlink_if_exists(file)
        if removed:
            prune_empty_dirs(self.root, file.parent)
        return removed

    # -- journal ----------------------------------------------------------
    def write_journal(self, journal: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.journal_path, json.dumps(journal, indent=2, ensure_ascii=False) + "\n")

    def read_journal(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.journal_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, UnicodeDecodeError):
            # The journal is written atomically, so this means on-disk corruption. Nothing
            # can be safely replayed; the caller quarantines it and leaves staging untouched.
            return {"actions": [], "corrupt": True}

    def quarantine_journal(self) -> Path:
        target = self.root / f".apply_journal.corrupt-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}.json"
        os.replace(self.journal_path, target)
        fsync_dir(self.root)
        return target

    def remove_empty_subdirs(self) -> None:
        if not self.root.is_dir():
            return
        for dirpath, dirnames, filenames in os.walk(self.root, topdown=False):
            if Path(dirpath) == self.root:
                continue
            try:
                os.rmdir(dirpath)
            except OSError:
                pass
        fsync_dir(self.root)


# ---------------------------------------------------------------------------
# diff()
# ---------------------------------------------------------------------------


def diff(ws: "Workspace", scope: str = "staging") -> dict[str, Any]:
    if scope not in ("staging", "overlay"):
        raise ValueError("scope must be 'staging' or 'overlay'")
    with ws._reading() as table:
        if scope == "staging":
            return _diff_staging(ws, table)
        return _diff_overlay(ws, table)


def _diff_staging(ws: "Workspace", table: "MountTable") -> dict[str, Any]:
    overlay = table.overlay
    items = []
    counts = {"create": 0, "modify": 0, "delete": 0, "conflicts": 0}
    history_details = ws.history.details()
    catalogs = ws.index.catalogs()
    for path, entry in ws.staging.entries().items():
        address = format_address(overlay.alias, path)
        current_text, current_sha = read_card_file(overlay.root / f"{path}.md")
        op = entry.get("op", "write")
        staged_text, staged_sha = (None, None) if op == "delete" else read_card_file(ws.staging.file(path))
        base = entry.get("base_sha256")
        conflict = precondition_conflict(base, current_sha)
        if op == "write" and staged_text is None:
            conflict = conflict or "staged file missing"
        change = "delete" if op == "delete" else ("create" if current_text is None else "modify")
        counts[change] += 1
        if conflict:
            counts["conflicts"] += 1
        item: dict[str, Any] = {
            "id": path,
            "address": address,
            "op": op,
            "change": change,
            "history": entry.get("history", []),
            "base_sha256": base,
            "current_sha256": current_sha,
            "staged_sha256": staged_sha,
            "conflict": conflict,
            "diff": unified(current_text, staged_text, f"a/{address}.md", f"b/{address}.md"),
        }
        parsed = parse_card(staged_text) if staged_text is not None else None
        targets = [address] + (supersede_targets(parsed, overlay.alias, catalogs) if parsed else [])
        item["impact"] = inbound_impact(ws.index, overlay.alias, overlay.precedence, targets, exclude=[address])
        item["references"] = {"extends": parsed.extends, "supersedes": parsed.supersedes,
                              "wikilinks": parsed.wikilink_targets()} if parsed else {}
        if entry.get("change_ids"):
            item["change_ids"] = entry["change_ids"]
            item["changes"] = ws.history.descriptions(entry["change_ids"], records=history_details)
        if entry.get("orphan"):
            item["orphan"] = True
        if entry.get("requires_approval"):
            item["requires_approval"] = entry["requires_approval"]
        items.append(item)
    return {
        "revision": hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "scope": "staging",
        "items": items,
        "summary": {"total": len(items), **counts},
        "clean": counts["conflicts"] == 0,
        "patch": "".join(i["diff"] for i in items),
    }


def _diff_overlay(ws: "Workspace", table: "MountTable") -> dict[str, Any]:
    idx = ws.index
    overlay = table.overlay
    items = []
    counts = {"new": 0, "shadow": 0, "extends": 0, "supersedes": 0, "unrebased": 0}
    history_details = ws.history.details()
    active = ws.history.applied()
    for row in idx.all_cards(overlay.alias):
        path = row["path"]
        address = format_address(overlay.alias, path)
        resolved: dict[str, list[str]] = {"extends": [], "supersedes": []}
        broken: list[str] = []
        for link in idx.outbound(overlay.alias, path):
            if link["kind"] not in resolved:
                continue
            if link["resolved"]:
                resolved[link["kind"]].append(format_address(link["dst_mount"], link["dst_path"]))
            else:
                broken.append(f"{link['kind']}: {link['raw']}")
        linked = set(resolved["extends"]) | set(resolved["supersedes"])
        shadows = [
            format_address(r["mount"], r["path"])
            for r in idx.cards_at_path(path)
            if r["mount"] != overlay.alias and format_address(r["mount"], r["path"]) not in linked
        ]
        if resolved["supersedes"]:
            kind, counterpart = "supersedes", resolved["supersedes"][0]
        elif resolved["extends"]:
            kind, counterpart = "extends", None
        elif shadows:
            kind, counterpart = "shadow", shadows[0]
        else:
            kind, counterpart = "new", None
        counts[kind] += 1
        current_text, _ = read_card_file(overlay.root / f"{path}.md")
        before_text = None
        if counterpart:
            mount, _, cpath = counterpart.partition("/")
            m = table.get(mount)
            if m is not None:
                before_text, _ = read_card_file(m.root / f"{cpath}.md")
        item: dict[str, Any] = {
            "id": path,
            "address": address,
            "kind": kind,
            "title": row["title"],
            "extends": resolved["extends"],
            "supersedes": resolved["supersedes"],
            "shadows": shadows,
            "sha256": row["sha256"],
        }
        tip, ids = active.get(address, (None, []))
        changes = ws.history.descriptions(ids, records=history_details) if tip == row["sha256"] else []
        if changes:
            item["changes"] = changes
            item["change_ids"] = [c["change_id"] for c in changes]
        if broken:
            item["unresolved"] = broken
        unrebased = []
        for base in resolved["extends"]:
            bmount, _, bpath = base.partition("/")
            replacements = [format_address(r["src_mount"], r["src_path"]) for r in idx.inbound("supersedes", bmount, bpath)]
            if replacements:
                unrebased.append({"baseline": base, "superseded_by": replacements})
        if unrebased:
            item["unrebased"] = unrebased
            counts["unrebased"] += 1
        before_label = f"a/{counterpart}.md" if counterpart else "/dev/null"
        item["diff"] = unified(before_text, current_text, before_label, f"b/{address}.md")
        items.append(item)
    return {"scope": "overlay", "items": items, "summary": {"total": len(items), **counts}}


# ---------------------------------------------------------------------------
# apply() / discard() / journal replay
# ---------------------------------------------------------------------------


def select_entries(entries: dict[str, Any], ids: list[str] | None) -> dict[str, Any]:
    """Select exact staging IDs; None means all, an empty list means none."""
    if ids is None:
        return dict(entries)
    if not isinstance(ids, (list, tuple)) or any(not isinstance(value, str) for value in ids):
        raise InvalidArgumentsError("card IDs must be a list of staging paths")
    selected = set()
    for value in ids:
        alias, path = parse_address(value)
        if alias not in (None, "@overlay"):
            raise InvalidArgumentsError("review targets must be staging IDs or @overlay/path", address=value)
        if path not in entries:
            raise InvalidArgumentsError("no pending change for this card; run mindslice diff", address=value)
        selected.add(path)
    return {path: entry for path, entry in entries.items() if path in selected}


def dependency_conflicts(ws, table, overrides):
    """Reject newly broken live links and references that need an unaccepted proposal.

    Existing unresolved links remain lint concerns, not blockers for unrelated reviews.
    Catalogs include aliases and obey the same slice-local resolution as normal reads.
    """
    alias = table.overlay.alias
    before = ws.index.catalogs()
    _, after = prospective_successors(ws.index, alias, overrides)
    _, proposed = prospective_successors(ws.index, alias, ws.staging.prospective_overrides(table.overlay.root))
    refs = []
    for mount in table.all():
        for row in ws.index.all_cards(mount.alias):
            path = row["path"]
            if mount.alias == alias and path in overrides:
                continue
            refs.extend((mount.alias, path, edge["kind"], edge["raw"])
                        for edge in ws.index.outbound(mount.alias, path))
    for path, parsed in overrides.items():
        if parsed is not None:
            for kind, values in (("extends", parsed.extends), ("supersedes", parsed.supersedes),
                                 ("wikilink", parsed.wikilink_targets())):
                refs.extend((alias, path, kind, raw) for raw in values)
    conflicts = []
    for source, path, kind, raw in refs:
        if resolve_ref(raw, source, after).resolved:
            continue
        previous = resolve_ref(raw, source, before)
        pending = resolve_ref(raw, source, proposed)
        selected = source == alias and path in overrides
        if previous.resolved or (selected and pending.resolved):
            target = previous.address if previous.resolved else pending.address
            conflicts.append({"address": format_address(source, path), "reason": "dependency",
                              "kind": kind, "target": target,
                              "detail": f"{kind} {raw!r} would not resolve. Accept its pending target or dependent "
                                        "edit together, or revise the reference before applying."})
    return conflicts


def apply(ws: "Workspace", ids: list[str] | None = None, *, reject: list[str] | None = None,
          revision: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    with ws._writing() as table:
        overlay = table.overlay
        staging = ws.staging
        all_entries = staging.entries()
        entries = select_entries(all_entries, ids)
        rejected = select_entries(all_entries, reject or [])
        if entries.keys() & rejected.keys():
            raise InvalidArgumentsError("a pending card cannot be both accepted and rejected")
        if revision is not None and revision != _diff_staging(ws, table)["revision"]:
            raise ApplyConflictError("review changed; run mindslice review again before accepting or rejecting",
                                     conflicts=[{"reason": "stale_review"}])
        if not entries and not rejected and not dry_run:
            return {"applied": 0, "created": [], "modified": [], "deleted": [], "skipped": []}
        conflicts: list[dict[str, Any]] = []
        overrides: dict[str, ParsedCard | None] = {}
        actions: list[dict[str, Any]] = []
        for path, entry in entries.items():
            address = format_address(overlay.alias, path)
            _, current_sha = read_card_file(overlay.root / f"{path}.md")
            base = entry.get("base_sha256")
            reason = precondition_conflict(base, current_sha)
            if reason:
                conflicts.append({"address": address, "reason": "precondition", "detail": reason,
                                  "base_sha256": base, "current_sha256": current_sha})
            if entry.get("op") == "delete":
                overrides[path] = None
                actions.append({"op": "delete", "id": path, "base_sha256": base})
                continue
            staged_text, staged_sha = read_card_file(staging.file(path))
            if staged_text is None:
                conflicts.append({"address": address, "reason": "staged_file_missing"})
                continue
            parsed = parse_card(staged_text)
            if parsed.errors:
                conflicts.append({"address": address, "reason": "invalid_card", "detail": "; ".join(parsed.errors)})
            overrides[path] = parsed
            actions.append({
                "op": "move", "id": path, "base_sha256": base, "sha256": staged_sha,
                "change": "create" if current_sha is None else "modify",
            })
        for path in [p for p, parsed in overrides.items() if parsed is not None]:
            try:
                check_cycles(ws.index, overlay.alias, overrides, [path])
            except LineageCycleError as exc:
                conflicts.append({"address": exc.details.get("address"), "reason": "lineage_cycle",
                                  "cycle": exc.details.get("cycle")})
                break
        # Legacy apply-all still allows deliberately dangling references, as write() does.
        # A selective review must not split a dependency across the approval boundary.
        if ids is not None or rejected:
            conflicts.extend(dependency_conflicts(ws, table, overrides))
        if dry_run:
            return {"ready": not conflicts, "conflicts": conflicts, "accept": list(entries),
                    "reject": list(rejected), "pending": sorted(set(all_entries) - entries.keys() - rejected.keys())}
        if conflicts:
            raise ApplyConflictError(
                f"apply aborted before touching overlay: {len(conflicts)} conflict(s)", conflicts=conflicts
            )
        for action in actions:
            action["entry"] = entries[action["id"]]
            ids = action["entry"].get("change_ids", [])
            fields = {"address": format_address(overlay.alias, action["id"]), "op": action["op"],
                      "before_sha256": action.get("base_sha256"), "after_sha256": action.get("sha256"),
                      "origin": "apply"}
            action["history_events"] = transitions("applied", ids, **fields) if ids else [change("applied", reason=None, **fields)]
        for path, entry in rejected.items():
            ids = entry.get("change_ids", [])
            fields = {"address": format_address(overlay.alias, path), "cause": "review"}
            events = transitions("discarded", ids, **fields) if ids else [change("discarded", **fields)]
            actions.append({"op": "discard", "id": path, "entry": entry,
                            "sha256": read_card_file(staging.file(path))[1], "history_events": events})
        journal = {"version": 1, "started_at": _now(), "overlay_root": str(overlay.root), "actions": actions}
        staging.write_journal(journal)
        return replay(ws, table, journal)


def replay(ws: "Workspace", table: "MountTable", journal: dict[str, Any]) -> dict[str, Any]:
    """Execute (or finish) a journaled batch idempotently. Caller holds ``LOCK_EX``.

    An action whose overlay target changed since it was journaled is skipped, never forced: it
    stays staged with its original ``base_sha256``, so ``diff()`` reports the conflict against the
    version the change was based on.
    """
    staging = ws.staging
    overlay_root = Path(journal.get("overlay_root") or table.overlay.root)
    alias = table.overlay.alias
    report: dict[str, Any] = {"applied": 0, "created": [], "modified": [], "deleted": [], "skipped": []}
    if any(a["op"] == "discard" for a in journal.get("actions", [])):
        report["discarded"] = 0
        report["discarded_ids"] = []
    skipped: list[dict[str, Any]] = []
    updated = False
    entries = staging.load_manifest()
    for action in journal.get("actions", []):
        if "history_events" not in action:
            action["entry"] = entries.get(action["id"], {})
            fields = {"address": format_address(alias, action["id"]), "op": action["op"],
                      "before_sha256": action.get("base_sha256"), "after_sha256": action.get("sha256"), "origin": "apply"}
            ids = action["entry"].get("change_ids", [])
            action["history_events"] = transitions("applied", ids, **fields) if ids else [change("applied", reason=None, **fields)]
            updated = True
    if updated:
        staging.write_journal(journal)
    recorded = {e["event_id"] for e in ws.history.events()}
    for action in journal.get("actions", []):
        path = action["id"]
        address = format_address(alias, path)
        dst = overlay_root / f"{path}.md"
        completed = all(e["event_id"] in recorded for e in action["history_events"])
        if completed and action["op"] == "discard":
            report["discarded"] += 1
            report["discarded_ids"].append(path)
            continue
        if completed:
            key = "deleted" if action["op"] == "delete" else ("created" if action.get("change") == "create" else "modified")
            report[key].append(address)
            report["applied"] += 1
            continue
        if action["op"] == "discard":
            current = read_card_file(staging.file(path))[1]
            if current is not None and current != action.get("sha256"):
                report["skipped"].append({"address": address, "reason": "staged file changed during recovery; kept"})
                skipped.append(action)
                continue
            staging._drop_file(staging.file(path))
            ws.history.append(action["history_events"])
            report["discarded"] += 1
            report["discarded_ids"].append(path)
            continue
        if action["op"] == "move":
            src = staging.file(path)
            if src.is_file():
                _, dst_sha = read_card_file(dst)
                if dst_sha not in (action.get("base_sha256"), action.get("sha256")):
                    report["skipped"].append({"address": address, "reason": "overlay changed during recovery; staged file kept"})
                    skipped.append(action)
                    continue
                if read_card_file(src)[1] != action.get("sha256"):
                    report["skipped"].append({"address": address, "reason": "staged file changed during recovery; kept"})
                    skipped.append(action)
                    continue
                durable_move(src, dst)
            elif read_card_file(dst)[1] != action.get("sha256"):
                report["skipped"].append({"address": address, "reason": "applied content missing or changed; history not confirmed"})
                skipped.append(action)
                continue
            report["created" if action.get("change") == "create" else "modified"].append(address)
        elif action["op"] == "delete":
            _, dst_sha = read_card_file(dst)
            if dst_sha is not None and dst_sha != action.get("base_sha256"):
                report["skipped"].append({"address": address, "reason": "overlay changed during recovery; delete kept staged"})
                skipped.append(action)
                continue
            if dst_sha is not None:
                unlink_if_exists(dst)
                prune_empty_dirs(overlay_root, dst.parent)
            report["deleted"].append(address)
        ws.history.append(action["history_events"])
        report["applied"] += 1
    ws._sync(table)  # (c) one SQLite transaction
    manifest = staging.load_manifest()
    remaining = {p: entry for p, entry in manifest.items()
                 if p not in {a["id"] for a in journal.get("actions", [])}}
    remaining.update(_skipped_entries(manifest, skipped))
    staging.save_manifest(remaining)  # preserve every unselected proposal, including during replay
    staging.remove_empty_subdirs()
    unlink_if_exists(staging.journal_path)  # (e) strictly last
    return report


def _skipped_entries(manifest: dict[str, dict[str, Any]], skipped: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Manifest entries to keep for skipped actions; rebuilt from the journal if an earlier pass removed them."""
    kept: dict[str, dict[str, Any]] = {}
    for action in skipped:
        entry = manifest.get(action["id"]) or action.get("entry")
        if not entry:
            entry = {"op": "delete" if action["op"] == "delete" else "write",
                     "base_sha256": action.get("base_sha256"), "history": [], "updated_at": _now()}
        kept[action["id"]] = entry
    return kept


def discard(ws: "Workspace", ids: list[str] | None = None) -> dict[str, Any]:
    with ws._writing():
        entries = select_entries(ws.staging.entries(), ids)
        events = []
        for path, entry in entries.items():
            ids = entry.get("change_ids", [])
            fields = {"address": format_address(ws.table().overlay.alias, path), "cause": "discard"}
            events += transitions("discarded", ids, **fields) if ids else [change("discarded", **fields)]
        remaining = {p: entry for p, entry in ws.staging.load_manifest().items() if p not in entries}
        actions = [file_action(ws.staging.file(p), None, ws.staging.root) for p in entries]
        if entries:
            actions.append(file_action(ws.staging.manifest_path, ws.staging.manifest_text(remaining)))
        if ids is None:
            actions = [file_action(p, None, ws.staging.root) for p in sorted(ws.staging.root.rglob("*")) if p.is_file()]
        if actions or events:
            ws.history.transact(actions, events)
        ws.staging.remove_empty_subdirs()
        return {"discarded": len(entries), "ids": list(entries)}
