"""Workspace overview for humans: mounts, pending review, and unbaked overlay changes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..storage.config import OVERVIEW_PATH
from .staging import _diff_overlay, _diff_staging

if TYPE_CHECKING:  # pragma: no cover
    from ..workspace import Workspace


def status(ws: "Workspace") -> dict[str, Any]:
    with ws._reading() as table:
        staged = _diff_staging(ws, table)
        pending = [{k: item[k] for k in ("address", "change", "conflict", "requires_approval", "orphan", "changes", "change_ids") if k in item}
                   for item in staged["items"]]
        changes = {m.alias: [] for m in table.mounts}
        unassigned = []
        for item in _diff_overlay(ws, table)["items"]:
            if item["id"] == OVERVIEW_PATH:
                continue
            relations: dict[str, set[str]] = {}
            for field, kind in (("extends", "extends"), ("supersedes", "supersedes"), ("shadows", "shadow")):
                for target in item[field]:
                    alias = target.partition("/")[0]
                    if alias in changes:
                        relations.setdefault(alias, set()).add(kind)
            entry = {k: item[k] for k in ("address", "kind", "unresolved", "unrebased", "changes", "change_ids") if k in item}
            if not relations:
                unassigned.append(entry)
            for alias, kinds in relations.items():
                changes[alias].append(dict(entry, kinds=sorted(kinds)))
        dirty = []
        mounts = []
        for mount in table.all():
            mounts.append({
                "alias": mount.alias, "path": mount.path, "precedence": mount.precedence, "role": mount.role,
                "kind": mount.kind, "card_count": ws.index.folder_counts(mount.alias)[2],
                "missing": not mount.root.is_dir(), "dirty": bool(changes.get(mount.alias)),
            })
            cards = changes.get(mount.alias, [])
            if cards:
                dirty.append({"alias": mount.alias, "cards": cards, "summary": {
                    "total": len(cards),
                    **{kind: sum(kind in c["kinds"] for c in cards) for kind in ("extends", "supersedes", "shadow")},
                }})
        return {
            "workspace": str(ws.root),
            "mounts": mounts,
            "pending_review": {"files": pending, "summary": staged["summary"]},
            "dirty_slices": dirty,
            "unassigned_overlay_cards": unassigned,
            "clean": not (pending or dirty or unassigned),
        }


def render_status(result: dict[str, Any]) -> str:
    lines = [f"Workspace: {result['workspace']}", "", f"Mounts ({len(result['mounts'])}):"]
    for mount in result["mounts"]:
        flags = [name for name in ("missing", "dirty") if mount[name]]
        if mount["kind"] == "overlay":
            flags.insert(0, "writable")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"  {mount['alias']}  {mount['path']}  precedence={mount['precedence']} "
                     f"role={mount['role']}  cards={mount['card_count']}{suffix}")
    pending = result["pending_review"]
    counts = pending["summary"]
    lines += ["", f"Pending review ({counts['total']}): "
              f"{counts['create']} added, {counts['modify']} modified, {counts['delete']} deleted, "
              f"{counts['conflicts']} conflicts"]
    for item in pending["files"]:
        lines.append(f"  {item['change']}  {item['address']}")
        for change in item.get("changes", []):
            if change.get("reason"):
                lines.append(f"    reason ({change['op']}): {change['reason']}")
        if item.get("requires_approval"):
            lines.append(f"    awaiting approval: {item['requires_approval']}")
        if item["conflict"]:
            lines.append(f"    conflict: {item['conflict']}")
    lines += ["", f"Dirty slices ({len(result['dirty_slices'])}; unbaked overlay changes):"]
    for item in result["dirty_slices"]:
        counts = item["summary"]
        lines.append(f"  {item['alias']}: {counts['total']} cards "
                     f"({counts['extends']} extends, {counts['supersedes']} supersedes, {counts['shadow']} shadows)")
        for card in item["cards"]:
            lines.append(f"    {card['address']} ({', '.join(card['kinds'])})")
            for change in card.get("changes", []):
                if change.get("reason"):
                    lines.append(f"      reason ({change['op']}): {change['reason']}")
    new = result["unassigned_overlay_cards"]
    lines += ["", f"Unassigned overlay cards ({len(new)}):"]
    for card in new:
        lines.append(f"  {card['address']}")
        for change in card.get("changes", []):
            if change.get("reason"):
                lines.append(f"    reason ({change['op']}): {change['reason']}")
    if pending["files"]:
        lines += ["", "Review with `mindslice diff`; accept with `mindslice apply` or drop with `mindslice discard`."]
    if result["clean"]:
        lines += ["", "No pending review or unbaked overlay changes."]
    return "\n".join(lines) + "\n"
