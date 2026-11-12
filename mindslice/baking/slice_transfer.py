"""Reference rewriting, dependency closure and overlay retirement shared by bake and mount.

Every reference (``extends``, ``supersedes``, ``[[wikilinks]]``) is first
resolved against ``@overlay`` (source-first), then classified:

* included ``@overlay`` target -> written slice-relative (``<path>``)
* external slice target        -> kept qualified (``@alias/<path>``) and listed
                                   under ``dependencies`` in ``slice.toml``
* excluded ``@overlay`` target -> ``UnresolvedExportDependencyError`` unless
                                   ``include_deps=True`` pulls it in transitively
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Sequence

from ..model.addressing import MountCatalog, format_address, resolve_ref, rewrite_wikilinks
from ..model.card import ParsedCard, normalize_newlines, parse_card
from ..errors import UnresolvedExportDependencyError
from ..storage.fsutil import iter_markdown
from ..storage.history import change, event, file_action
from ..storage.card_io import read_card_file
from ..model.card import reassemble

if TYPE_CHECKING:  # pragma: no cover
    from ..workspace import Workspace


def rewrite_refs(text: str, parsed: ParsedCard, mapper: Callable[[str], str]) -> str:
    """``text`` with every ``extends`` / ``supersedes`` / ``[[wikilink]]`` reference passed through ``mapper``.

    Parts no reference touches are kept byte for byte (``reassemble``).
    """
    new_ext = [mapper(r) for r in parsed.extends]
    new_sup = [mapper(r) for r in parsed.supersedes]
    fields = None
    if new_ext != parsed.extends or new_sup != parsed.supersedes:
        fields = dict(parsed.frontmatter)
        fields["extends"], fields["supersedes"] = new_ext, new_sup
    link_map = {t: mapper(t) for t in parsed.wikilink_targets()}
    link_map = {k: v for k, v in link_map.items() if k != v}
    new_after = rewrite_wikilinks(parsed.after, link_map) if link_map else None
    return reassemble(parsed, text, fields, new_after)


def export_text(text: str, parsed: ParsedCard, overlay_alias: str, cats: dict[str, MountCatalog]) -> str:
    """The file a new ``bake()`` writes for one overlay card (source-first reference rewriting)."""

    def rewrite(raw: str) -> str:
        res = resolve_ref(raw, overlay_alias, cats)
        if res.mount == overlay_alias:
            if raw.strip().startswith("@") and res.path:
                return res.path  # @overlay/x -> slice-relative x
            return raw  # slice-relative refs keep resolving inside the exported slice
        if res.mount and res.resolved and res.path:
            return format_address(res.mount, res.path)  # canonical qualified external ref
        return raw

    return rewrite_refs(text, parsed, rewrite)


def overlay_cards(ws: "Workspace", table) -> dict[str, tuple[str, ParsedCard]]:
    """Every ``@overlay`` card from disk (``{path: (text, parsed)}``), skipping mounts nested inside it."""
    overlay = table.overlay
    nested = tuple(o.root for o in table.all() if o.alias != overlay.alias and overlay.root in o.root.parents)
    cards: dict[str, tuple[str, ParsedCard]] = {}
    for rel, _ in iter_markdown(overlay.root, exclude=tuple(ws._exclude()) + nested):
        text, _ = read_card_file(overlay.root / f"{rel}.md")
        if text is not None:
            cards[rel] = (text, parse_card(text))
    return cards


def dependency_closure(
    cards: dict[str, tuple[str, ParsedCard]],
    selected: Sequence[str],
    overlay_alias: str,
    cats: dict[str, MountCatalog],
    include_deps: bool,
) -> tuple[set[str], list[str], set[str], list[str]]:
    """``(included, pulled, external_mounts, warnings)`` for exporting ``selected`` overlay cards.

    A reference to an overlay card outside the selection raises ``UnresolvedExportDependencyError``,
    unless ``include_deps`` pulls it in (transitively; ``pulled`` lists those).
    """
    included = set(selected)
    pulled: list[str] = []
    missing: list[dict[str, str]] = []
    warnings: list[str] = []
    external: set[str] = set()
    queue = list(selected)
    while queue:
        path = queue.pop(0)
        parsed = cards[path][1]
        refs = [(k, r) for k in ("extends", "supersedes") for r in parsed.list_field(k)]
        refs += [("wikilink", r) for r in parsed.wikilink_targets()]
        for kind, raw in refs:
            res = resolve_ref(raw, overlay_alias, cats)
            if res.mount is None:
                warnings.append(f"{path}: {kind} reference {raw!r} is not a valid address; copied verbatim")
                continue
            if res.mount != overlay_alias:
                external.add(res.mount)
                if not res.resolved:
                    warnings.append(f"{path}: {kind} reference {raw!r} does not resolve in {res.mount}")
                continue
            if not res.resolved or res.path not in cards:
                warnings.append(f"{path}: {kind} reference {raw!r} does not resolve in {overlay_alias}; copied verbatim")
                continue
            if res.path in included:
                continue
            if include_deps:
                included.add(res.path)
                pulled.append(res.path)
                queue.append(res.path)
            else:
                missing.append({"source": format_address(overlay_alias, path), "field": kind, "ref": raw,
                                "target": format_address(overlay_alias, res.path)})
    if missing:
        targets = sorted({m["target"] for m in missing})
        raise UnresolvedExportDependencyError(
            f"export references {len(targets)} excluded {overlay_alias} card(s): {', '.join(targets)} "
            "(pass include_deps=True to pull them in)",
            missing=missing,
        )
    return included, pulled, external, warnings


def retire_copies(ws: "Workspace", table, alias: str) -> dict[str, Any]:
    """Remove the ``@overlay`` cards that the newly mounted slice ``alias`` holds unchanged.

    Imported slices may contain copies of overlay cards; once its slice is mounted, the copies left in ``@overlay`` (higher
    precedence) would shadow it and turn every ``supersedes`` they carry into competing replacements.
    An overlay card is retired when the export transform of it is exactly the slice's card at the
    same path: nothing is lost, the slice holds it. It is kept (and reported) when it differs (edited
    since, or not an exported copy), when it has a staged change, or when a staged card references it.
    References to a retired card from overlay cards that stay are rewritten to its new address
    (``[[db/pool]]`` -> ``[[@db/db/pool]]``), so links and lineage keep their targets; references from
    read-only mounts can't be rewritten and are reported. Runs under the caller's ``LOCK_EX``; the
    caller syncs the index afterwards.
    """
    overlay = table.overlay
    mount = table.get(alias)
    idx = ws.index
    cats = idx.catalogs()
    staged = set(ws.staging.entries())
    slice_paths = {r["path"] for r in idx.all_cards(alias)}
    overlay_paths = {r["path"] for r in idx.all_cards(overlay.alias)}
    retired: list[str] = []
    kept: list[dict[str, str]] = []
    for path in sorted(slice_paths & overlay_paths):
        o_text, _ = read_card_file(overlay.root / f"{path}.md")
        s_text, _ = read_card_file(mount.root / f"{path}.md")
        if o_text is None or s_text is None:
            continue
        address = format_address(overlay.alias, path)
        if path in staged:
            kept.append({"address": address, "reason": "staged change pending"})
            continue
        exported = normalize_newlines(export_text(o_text, parse_card(o_text), overlay.alias, cats))
        if normalize_newlines(s_text) not in (exported, normalize_newlines(o_text)):
            kept.append({"address": address, "reason": f"differs from {format_address(alias, path)}"})
            continue
        retired.append(path)
    return retire_overlay_paths(ws, table, alias, retired, kept, cats)


def retire_overlay_paths(ws: "Workspace", table, alias: str, retired: list[str], kept: list[dict[str, str]],
                         cats: dict[str, MountCatalog], *, actions: list | None = None,
                         events: list | None = None) -> dict[str, Any]:
    """Remove the ``@overlay`` cards at ``retired`` paths, now held by slice ``alias`` at the same paths.

    References to them from overlay cards that stay are rewritten to ``@alias/<path>``; a card that a
    staged card references is kept instead (rewriting the overlay file would conflict) and added to
    ``kept``. Runs under the caller's ``LOCK_EX``; the caller syncs the index afterwards.
    """
    own_transaction = actions is None
    actions = [] if actions is None else actions
    events = [] if events is None else events
    overlay = table.overlay
    idx = ws.index
    staged = set(ws.staging.entries())
    retired = list(retired)
    kept = list(kept)

    def referrers(path: str) -> list[tuple[str, str, str]]:
        out = []
        for kind in ("extends", "supersedes", "wikilink"):
            out += [(kind, r["src_mount"], r["src_path"]) for r in idx.inbound(kind, overlay.alias, path)]
        return out

    blocked = True
    while blocked:  # a staged card that references a copy keeps it (rewriting the overlay file would conflict)
        blocked = False
        for path in list(retired):
            stager = next((f"{m}/{p}" for _, m, p in referrers(path)
                           if m == overlay.alias and p in staged and p not in retired), None)
            if stager:
                retired.remove(path)
                kept.append({"address": format_address(overlay.alias, path), "reason": f"referenced by staged {stager}"})
                blocked = True
    retired_set = set(retired)

    def mapper(raw: str) -> str:
        res = resolve_ref(raw, overlay.alias, cats)
        if res.resolved and res.mount == overlay.alias and res.path in retired_set:
            return format_address(alias, res.path)
        return raw

    rebased: list[dict[str, str]] = []
    broken: list[dict[str, str]] = []
    to_rewrite: set[str] = set()
    for path in retired:
        target = format_address(overlay.alias, path)
        for kind, src_mount, src_path in referrers(path):
            if src_mount == overlay.alias:
                if src_path not in retired_set:
                    to_rewrite.add(src_path)
                continue
            for link in idx.outbound(src_mount, src_path, kind):
                if link["resolved"] and format_address(link["dst_mount"], link["dst_path"]) == target:
                    item = {"address": format_address(src_mount, src_path), "kind": kind, "ref": link["raw"]}
                    if item not in broken:
                        broken.append(item)
    for src_path in sorted(to_rewrite):
        text, _ = read_card_file(overlay.root / f"{src_path}.md")
        if text is None:
            continue
        parsed = parse_card(text)
        address = format_address(overlay.alias, src_path)
        refs = [(k, r) for k in ("extends", "supersedes") for r in parsed.list_field(k)]
        refs += [("wikilink", r) for r in parsed.wikilink_targets()]
        changes = [{"address": address, "kind": k, "ref": r, "to": mapper(r)} for k, r in refs if mapper(r) != r]
        if parsed.errors:
            broken += [{"address": address, "kind": c["kind"], "ref": c["ref"]} for c in changes]
            continue
        new_text = rewrite_refs(text, parsed, mapper)
        if new_text != normalize_newlines(text):
            action = file_action(overlay.root / f"{src_path}.md", new_text)
            actions.append(action)
            events.append(change("applied", address=address, op="rebase", origin="engine",
                                 reason=f"Rebase references to cards moved into {alias}",
                                 before_sha256=action["before_sha256"], after_sha256=action["after_sha256"]))
            rebased += changes
    for path in retired:
        file = overlay.root / f"{path}.md"
        actions.append(file_action(file, None, overlay.root))
    out: dict[str, Any] = {}
    if retired:
        out["retired_overlay_cards"] = [format_address(overlay.alias, p) for p in retired]
    if kept:
        out["shadowing_overlay_cards"] = sorted(kept, key=lambda k: k["address"])
    if rebased:
        out["rebased_references"] = rebased
    if broken:
        out["broken_references"] = sorted(broken, key=lambda b: (b["address"], b["kind"], b["ref"]))
    if own_transaction and (actions or events):
        events.append(event("retired", alias=alias, path=str(table.get(alias).root),
                            retired_overlay_cards=out.get("retired_overlay_cards", [])))
        ws.history.transact(actions, events)
    return out

