"""Human-readable renderings of CLI results; ``--json`` prints the underlying dicts instead."""

from __future__ import annotations

import json
from typing import Any, Callable

Renderer = Callable[[dict[str, Any]], str]


def _join(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def _refs(items: list[Any]) -> str:
    """Comma-separated addresses from a list of addresses or ``{"address": ...}`` dicts."""
    return ", ".join(item["address"] if isinstance(item, dict) else str(item) for item in items)


def _more(shown: int, total: int, flag: str, next_offset: int | None) -> str:
    if next_offset is None or total <= shown:
        return ""
    return f" (+{total - shown} more; {flag} {next_offset})"


def _sync(sync: dict[str, Any]) -> str:
    return f"index: {sync['added']} added, {sync['updated']} updated, {sync['removed']} removed"


# --- read / search -----------------------------------------------------------------------------


def render_read(result: dict[str, Any]) -> str:
    """Composed view of a ``read()`` result: baselines, the card, extensions, then lineage notices."""
    out: list[str] = []

    def card(c: dict[str, Any], heading: str) -> None:
        out.append(f"{heading} {c['title']}  ({c['address']}, role={c['role']}, precedence={c['precedence']})")
        if c.get("summary"):
            out.append("")
            out.append(c["summary"])
        if c.get("body", "").strip():
            out.append("")
            out.append(c["body"].rstrip())
        out.append("")

    notes = []
    if result.get("redirected_from"):
        notes.append("redirected from " + result["redirected_from"] + " via " + " -> ".join(result.get("lineage_path", [])))
    for key in ("shadows", "superseded_by_untrusted", "baseline_superseded_by", "missing_baselines"):
        if result.get(key):
            notes.append(f"{key}: {', '.join(result[key])}")
    if result.get("unrebased_extensions"):
        notes.append("unrebased_extensions: " + ", ".join(
            f"{u['address']} (extends {u['extends']})" for u in result["unrebased_extensions"]))
    if result.get("bypassed_replacements"):
        notes.append("bypassed_replacements: " + ", ".join(
            f"{b['address']} (supersedes {b['supersedes']})" for b in result["bypassed_replacements"]))
    if result.get("competing_replacements"):
        notes.append("competing_replacements: " + _refs(result["competing_replacements"]))
    if result.get("unresolved_refs"):
        notes.append("unresolved_refs: " + ", ".join(map(str, result["unresolved_refs"])))
    for error in result.get("parse_errors", []):
        notes.append("parse_error: " + error)
    if result.get("extensions_next_offset") is not None:
        shown = len(result.get("extensions", []))
        notes.append(f"extensions: showing {shown} of {result['total_extensions']}; "
                     f"more with --extensions-offset {result['extensions_next_offset']}")
    if result.get("backlinks"):
        notes.append("backlinks: " + _refs(result["backlinks"])
                     + _more(len(result["backlinks"]), result.get("total_backlinks", 0),
                             "--backlinks-offset", result.get("backlinks_next_offset")))
    for base in result.get("baselines", []):
        card(base, "## Baseline:")
    card(result, "#")
    for ext in result.get("extensions", []):
        card(ext, "## Extension:")
    if notes:
        out.append("---")
        out.extend(f"> {n}" for n in notes)
        out.append("")
    out.append(f"status: {result.get('status')}  sha256: {result.get('sha256')}")
    return _join(out)


_SEARCH_NOTES = ("resolves_to", "matched_via_superseded", "supersedes", "extends", "superseded_by",
                 "superseded_by_untrusted", "baseline_superseded_by", "missing_baselines")


def render_search(result: dict[str, Any]) -> str:
    hits = result["results"]
    query = json.dumps(result["query"], ensure_ascii=False)
    if not hits:
        lines = [f"No matches for {query}." if not result["total_matches"]
                 else f"No matches for {query} at offset {result['offset']} ({result['total_matches']} total)."]
    else:
        first = result["offset"] + 1
        lines = [f"Matches {first}-{result['offset'] + len(hits)} of {result['total_matches']} for {query}"
                 + (f"; next page: --offset {result['next_offset']}" if result.get("next_offset") is not None else ""),
                 ""]
    for n, hit in enumerate(hits, result["offset"] + 1):
        marks = [f"tags: {', '.join(hit['tags'])}"] if hit.get("tags") else []
        if hit.get("load"):
            marks.append(f"load: {hit['load']}")
        lines.append(f"{n}. {hit['address']} — {hit['title']}" + (f"  [{'; '.join(marks)}]" if marks else ""))
        if hit.get("summary"):
            lines.append(f"   {hit['summary']}")
        if hit.get("status", "active") != "active":
            lines.append(f"   status: {hit['status']}")
        for key in _SEARCH_NOTES:
            if hit.get(key):
                value = hit[key] if isinstance(hit[key], list) else [hit[key]]
                lines.append(f"   {key.replace('_', ' ')}: {_refs(value)}")
        if hit.get("bypassed_replacements"):
            lines.append("   bypassed replacements: " + ", ".join(
                f"{b['address']} (supersedes {b['supersedes']})" for b in hit["bypassed_replacements"]))
        if hit.get("competing_replacements"):
            lines.append("   competing replacements: " + _refs(hit["competing_replacements"]))
        if hit.get("neighbors"):
            extra = hit["total_neighbors"] - len(hit["neighbors"])
            lines.append("   related: " + ", ".join(f"{nb['address']} ({nb['direction']})" for nb in hit["neighbors"])
                         + (f" (+{extra} more)" if extra > 0 else ""))
    if result.get("unmatched_terms"):
        lines += ["", "No card in scope contains: " + ", ".join(result["unmatched_terms"])]
    return _join(lines)


# --- writes ----------------------------------------------------------------------------------


_VERBS = {"create": "Created", "replace": "Replaced", "append": "Appended to", "delete": "Deleted"}


def render_write(result: dict[str, Any]) -> str:
    address, op = result["address"], result["op"]
    if not result["changed"]:
        lines = [f"No change: {address}"]
    elif result["staged"]:
        lines = [f"Staged {op}: {address} (pending review, not active yet)"]
        if result.get("requires_approval"):
            lines.append(f"Awaiting approval: {result['requires_approval']}")
        else:
            lines.append(f"Review with `mindslice diff`; accept with `mindslice apply {result['id']}`.")
    else:
        lines = [f"{_VERBS.get(op, op)} {address}"]
    if result.get("sha256"):
        lines.append(f"sha256: {result['sha256']}")
    if result.get("reason"):
        lines.append(f"reason: {result['reason']}")
    for key in ("affected_backlinks", "affected_extensions"):
        if result.get(key):
            total = result.get("total_" + key, len(result[key]))
            lines.append(f"{key.replace('_', ' ')} ({total}): {_refs(result[key])}")
    lines += [f"warning: {w}" for w in result.get("warnings", [])]
    return _join(lines)


def render_apply(result: dict[str, Any]) -> str:
    if not result["applied"] and not result.get("discarded") and not result["skipped"]:
        lines = ["Nothing applied."]
    else:
        lines = [f"Applied {result['applied']} pending change(s); active now."]
    for key in ("created", "modified", "deleted"):
        lines += [f"  {key}: {address}" for address in result[key]]
    if result.get("discarded"):
        lines.append(f"Rejected {result['discarded']} proposal(s): {', '.join(result.get('discarded_ids', []))}")
    lines += [f"  skipped: {item['address']}: {item['reason']}" for item in result["skipped"]]
    return _join(lines)


def render_discard(result: dict[str, Any]) -> str:
    if not result["discarded"]:
        return "Nothing discarded.\n"
    return _join([f"Discarded {result['discarded']} pending proposal(s); live memory unchanged."]
                 + [f"  {item}" for item in result["ids"]])


def render_review(result: dict[str, Any]) -> str:
    if result.get("cancelled"):
        lines = ["Review cancelled; nothing changed."]
        lines += [f"  blocked: {c.get('address', '')}: {c.get('detail', c['reason'])}" for c in result.get("conflicts", [])]
        return _join(lines)
    if "created" not in result:
        return f"Nothing reviewed; {result['remaining']} pending change(s) remain.\n"
    return render_apply(result) + f"Pending: {result['remaining']} change(s) remain.\n"


# --- workspace and mounts ----------------------------------------------------------------------


def render_init(result: dict[str, Any]) -> str:
    return _join([f"Initialized workspace: {result['workspace']}", f"Mount table: {result['mounts']}",
                  f"Next: mindslice -w {result['workspace']} doctor"])


def render_mount(result: dict[str, Any]) -> str:
    lines = [f"Mounted {result['alias']}: {result['path']}",
             f"precedence={result['precedence']} role={result['role']} cards={result['cards']}  ({_sync(result['sync'])})"]
    if result.get("retired_overlay_cards"):
        lines.append(f"Retired {len(result['retired_overlay_cards'])} unchanged overlay copies: "
                     + ", ".join(result["retired_overlay_cards"]))
    for key, value in result.items():
        if key.endswith("warnings") and value:
            lines += [f"warning: {w if isinstance(w, str) else w.get('message', w)}" for w in value]
    return _join(lines)


def render_unmount(result: dict[str, Any]) -> str:
    return f"Unmounted {result['alias']}; {result['removed_cards']} cards left the index. The directory is untouched.\n"


def render_validate(result: dict[str, Any]) -> str:
    stats = result["stats"]
    lines = [f"{'OK' if result['ok'] else 'FAILED'}: {result['target']}",
             f"{stats['slices']} slice(s), {stats['cards']} card(s), {stats['errors']} error(s), {stats['warnings']} warning(s)"]
    for issue in result["errors"] + result["warnings"]:
        where = issue.get("address") or issue.get("file")
        lines.append(f"  {issue['severity']} [{issue['code']}] " + (f"{where}: " if where else "") + issue["message"])
    if result.get("rebuilt_index"):
        lines.append("Index rebuilt: " + ", ".join(f"{k}={v}" for k, v in result["rebuilt_index"].items()
                                                  if not isinstance(v, (dict, list))))
    return _join(lines)


def render_manifest(result: dict[str, Any]) -> str:
    lines = []
    for mount in result["mounts"]:
        head = f"{mount['alias']}  {mount['card_count']} cards  precedence={mount['precedence']} role={mount['role']}"
        if mount.get("version"):
            head += f"  v{mount['version']}"
        if mount["writable"]:
            head += "  [writable]"
        if mount.get("missing"):
            head += "  [missing]"
        lines.append(head)
        if mount.get("description"):
            lines.append(f"  {mount['description']}")
        lines.append(f"  path: {mount['path']}")
        if mount.get("dependencies"):
            lines.append(f"  dependencies: {', '.join(mount['dependencies'])}")
        if mount.get("missing_dependencies"):
            lines.append(f"  missing dependencies: {', '.join(mount['missing_dependencies'])}")
        lines += [f"  manifest error: {e}" for e in mount.get("manifest_errors", [])]
        if mount.get("root_cards"):
            lines.append(f"  (root): {mount['root_cards']} cards")
        lines += [f"  {folder['name']}/: {folder['cards']} cards" for folder in mount["folders"]]
        if mount.get("folders_truncated"):
            lines.append(f"  ... {mount['total_folders'] - len(mount['folders'])} more folders (--max-folders)")
        if mount.get("overview"):
            lines += [""] + [f"  {line}".rstrip() for line in mount["overview"].splitlines()]
        lines.append("")
    if result.get("next_offset") is not None:
        lines.append(f"{result['total_mounts'] - result['offset'] - len(result['mounts'])} more mounts: "
                     f"--offset {result['next_offset']}")
    if result.get("always_loaded"):
        lines.append("Always-loaded cards: " + _refs(result["always_loaded"]))
    if result.get("onboarding_hint"):
        lines.append("Workspace is empty: mount a notes folder or write a card to get started.")
    staging = result.get("staging") or {}
    if staging.get("pending"):
        lines.append(f"Pending review: {staging['pending']} change(s); see `mindslice diff`.")
        lines += [f"  awaiting approval: {item['id']} ({item['reason']})" for item in staging.get("awaiting_approval", [])]
    return _join(lines)


def render_bake(result: dict[str, Any]) -> str:
    """Single-slice bake (``bake @alias``) plan or receipt."""
    dry = result["dry_run"]
    action = "update" if result.get("previous_path") else "create"
    lines = [f"{'Would ' + action if dry else ('Updated' if action == 'update' else 'Created')} "
             f"{result['alias']} v{result['version']}: {result['output']}"
             + (f" ({result['format']})" if result.get("format") not in (None, "directory") else "")]
    if result.get("path") and result["path"] != result["output"]:
        lines.append(f"mounted directory: {result['path']}")
    if result.get("previous_path"):
        lines.append(f"previous version: {result['previous_path']} (left as it was)")
    lines.append(f"cards ({len(result['cards'])}): {', '.join(result['cards'])}")
    for key in ("created", "replaced", "included_dependencies", "retired_overlay_cards"):
        if result.get(key):
            lines.append(f"{key.replace('_', ' ')}: {', '.join(result[key])}")
    if result.get("dependencies"):
        added = result.get("dependencies_added") or []
        lines.append(f"dependencies: {', '.join(result['dependencies'])}" + (f" (new: {', '.join(added)})" if added else ""))
    lines += [f"warning: {w if isinstance(w, str) else w.get('message', w)}" for w in result.get("warnings", [])]
    validation = result.get("validation")
    if validation:
        lines.append(f"validation: {'ok' if validation['ok'] else 'FAILED'}"
                     + (f", {validation['warnings']} warning(s)" if validation.get("warnings") else ""))
        lines += [f"  error: {e.get('message', e) if isinstance(e, dict) else e}" for e in validation.get("errors", [])]
    if dry:
        lines.append("Dry run: nothing was written.")
    return _join(lines)


def render_cancelled(result: dict[str, Any]) -> str:
    lines = ["Cancelled; nothing changed."]
    if result.get("plan_path"):
        lines.append(f"Destination choices saved in {result['plan_path']}")
    return _join(lines)


# --- errors ------------------------------------------------------------------------------------


def render_error(error: dict[str, Any]) -> str:
    """``error [code]: message`` plus readable details, for stderr."""
    head = f"error [{error['code']}]: {error['message']}" if error.get("code") else f"error: {error['message']}"
    lines = [head]
    for key, value in (error.get("details") or {}).items():
        if key == "plan" and isinstance(value, dict):
            if "slices" in value:
                from .bake_review import render_plan
                lines.append(render_plan(value).rstrip())
            elif "previous_path" in value:
                from ..operations.recovery import render_rollback
                lines.append(render_rollback(value).rstrip())
            continue
        if key == "conflicts" and isinstance(value, list):
            lines += [f"  conflict: {c.get('address', '')}: {c.get('detail', c.get('reason', ''))}".replace(":  ", ": ")
                      if isinstance(c, dict) else f"  conflict: {c}" for c in value]
            continue
        if isinstance(value, list) and all(isinstance(v, (str, int, float)) for v in value):
            text = ", ".join(map(str, value))
        elif isinstance(value, list) and all(isinstance(v, dict) and "address" in v for v in value):
            text = _refs(value)
        elif isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
        lines.append(f"  {key}: {text}")
    return _join(lines)
