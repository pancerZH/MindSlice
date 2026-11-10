"""Group A read primitives: ``manifest()``, ``search()`` and ``read()`` (design section 4)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Iterable, Sequence

from .addressing import format_address, normalize_alias, parse_address
from .card import KNOWN_FIELDS, LOAD_ALWAYS, SUMMARY_PREVIEW_CHARS, parse_card, truncate
from .config import DESCRIPTION_CHARS, OVERVIEW_PATH, MountTable, load_slice_manifest
from .errors import InvalidAddressError, NotFoundError
from .lineage import FollowSpec, LineageView, TrustPolicy
from .writer import read_card_file

if TYPE_CHECKING:  # pragma: no cover
    from .workspace import Workspace

_LINEAGE_KINDS = ("extends", "supersedes")


def _nonneg(**values: int) -> None:
    for name, value in values.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")


def _split(address: str) -> tuple[str, str]:
    mount, _, path = address.partition("/")
    return mount, path


def _collapse(text: str) -> str:
    return " ".join((text or "").split())


def _page(total: int, offset: int, limit: int) -> int | None:
    return offset + limit if offset + limit < total else None


def _as_str_list(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


# ---------------------------------------------------------------------------
# manifest()
# ---------------------------------------------------------------------------


def manifest(
    ws: "Workspace",
    limit: int = 20,
    offset: int = 0,
    max_folders_per_mount: int = 10,
    include_overview: bool = False,
    include_always: bool = True,
) -> dict[str, Any]:
    """Mount map; on the first page (``offset=0``) also the always-loaded cards (``always_loaded``)."""
    from .boot import snapshot  # boot builds on this module

    _nonneg(limit=limit, offset=offset, max_folders_per_mount=max_folders_per_mount)
    with ws._reading() as table:
        idx = ws.index
        mounts = table.all()
        mounted = {m.alias for m in mounts}
        page = mounts[offset : offset + limit]
        out = []
        for m in page:
            sm = load_slice_manifest(m.root)
            folders, root_cards, total = idx.folder_counts(m.alias)
            overview = idx.card(m.alias, OVERVIEW_PATH)
            entry_card = overview if overview is not None else _readme(idx, m.alias)
            description = sm.description or (entry_card["preview"] if entry_card is not None else "")
            description, desc_truncated = truncate(_collapse(description), DESCRIPTION_CHARS)
            entry: dict[str, Any] = {
                "alias": m.alias,
                "role": m.role,
                "precedence": m.precedence,
                "kind": m.kind,
                "writable": m.writable,
                "path": m.path,
                "name": sm.name or m.root.name,
                "description": description,
                "card_count": total,
                "root_cards": root_cards,
                "folders": [{"name": name, "cards": count} for name, count in folders[:max_folders_per_mount]],
                "total_folders": len(folders),
                "folders_truncated": len(folders) > max_folders_per_mount,
                "has_overview": overview is not None,
            }
            if sm.version:
                entry["version"] = sm.version
            if desc_truncated:
                entry["description_truncated"] = True
            if sm.dependencies:
                entry["dependencies"] = list(sm.dependencies)
                missing = []
                for dep in sm.dependencies:
                    try:
                        if normalize_alias(dep) not in mounted:
                            missing.append(dep)
                    except InvalidAddressError:
                        missing.append(dep)
                if missing:
                    entry["missing_dependencies"] = missing
            if sm.errors:
                entry["manifest_errors"] = sm.errors
            if not m.root.is_dir():
                entry["missing"] = True
            if include_overview and overview is not None:
                text, _ = read_card_file(m.root / f"{OVERVIEW_PATH}.md")
                if text is not None:
                    entry["overview"] = parse_card(text).after.strip()
            out.append(entry)
        result: dict[str, Any] = {
            "mounts": out,
            "total_mounts": len(mounts),
            "offset": offset,
            "limit": limit,
            "truncated": offset + limit < len(mounts),
            "next_offset": _page(len(mounts), offset, limit),
        }
        pending = len(ws.staging.entries())
        if pending:
            result["staging"] = {"pending": pending}
        if include_always and offset == 0:
            boot = snapshot(ws, table)
            if boot["cards"]:
                result["always_loaded"] = boot["cards"]
            if boot.get("pending_approval"):
                result["staging"]["awaiting_approval"] = boot["pending_approval"]
        return result


def _readme(idx, mount: str):
    """A plain folder's README at its root: its description when there is no slice.toml or overview."""
    for name in ("README", "readme", "Readme"):
        row = idx.card(mount, name)
        if row is not None:
            return row
    return None


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


class _Ctx:
    """Per-request helper bundling the index, mount table and lineage view."""

    def __init__(self, ws: "Workspace", table: MountTable, follow: FollowSpec) -> None:
        self.ws = ws
        self.table = table
        self.idx = ws.index
        self.lv = LineageView(self.idx, TrustPolicy(follow))
        self._rows: dict[str, Any] = {}
        self._outbound: dict[str, list[Any]] = {}

    def row(self, address: str):
        if address not in self._rows:
            self._rows[address] = self.idx.card(*_split(address))
        return self._rows[address]

    def remember(self, row) -> str:
        address = format_address(row["mount"], row["path"])
        self._rows.setdefault(address, row)
        return address

    def outbound(self, address: str) -> list[Any]:
        if address not in self._outbound:
            self._outbound[address] = self.idx.outbound(*_split(address))
        return self._outbound[address]

    def lineage_targets(self, address: str, kind: str) -> list[str]:
        return [
            format_address(l["dst_mount"], l["dst_path"])
            for l in self.outbound(address)
            if l["kind"] == kind and l["resolved"]
        ]

    def unresolved_refs(self, address: str) -> list[dict[str, str]]:
        return [{"kind": l["kind"], "ref": l["raw"]} for l in self.outbound(address) if not l["resolved"]]

    def brief(self, address: str, summary_chars: int = SUMMARY_PREVIEW_CHARS) -> dict[str, Any]:
        row = self.row(address)
        if row is None:
            return {"address": address, "missing": True}
        summary, cut = truncate(_collapse(row["preview"]), summary_chars)
        out = {
            "address": address,
            "role": row["role"],
            "precedence": row["precedence"],
            "title": row["title"],
            "summary": summary,
        }
        if cut:
            out["summary_truncated"] = True
        return out

    def status(self, address: str) -> dict[str, Any]:
        """Supersession status fields shared by search previews and read results."""
        out: dict[str, Any] = {}
        fwd = self.lv.forward(address)
        direct = self.lv.all_superseders(address)
        untrusted = self.lv.untrusted_superseders(address)
        if fwd.competing:
            out["status"] = "competing_replacements"
            out["competing_replacements"] = [self.brief(a) for a in fwd.terminals]
        elif direct:
            out["status"] = "superseded_by: " + ", ".join(direct)
        else:
            out["status"] = "active"
        if direct:
            out["superseded_by"] = direct
        if untrusted:
            out["superseded_by_untrusted"] = untrusted
        if fwd.cycle:
            out["lineage_cycle"] = True
        return out

    def bypassed_replacements(self, *starts: str) -> list[dict[str, str]]:
        """Untrusted replacements of the cards a redirect from ``starts`` was forwarded through.

        The trust policy skipped them; the landing card's own untrusted replacements are reported
        separately, in ``superseded_by_untrusted``.
        """
        out: list[dict[str, str]] = []
        for start in starts:
            for old in sorted(self.lv.forward(start).superseded):
                for alt in self.lv.untrusted_superseders(old):
                    item = {"address": alt, "supersedes": old}
                    if item not in out:
                        out.append(item)
        return out

    def card_payload(self, address: str) -> dict[str, Any]:
        row = self.row(address)
        mount = self.table.get(row["mount"]) if row is not None else None
        if row is None or mount is None:
            raise NotFoundError(f"{address} not found", address=address)
        text, sha = read_card_file(mount.root / f"{row['path']}.md")
        if text is None:
            raise NotFoundError(f"{address} vanished from disk", address=address)
        parsed = parse_card(text)
        payload: dict[str, Any] = {
            "address": address,
            "mount": row["mount"],
            "path": row["path"],
            "role": row["role"],
            "precedence": row["precedence"],
            "title": parsed.display_title(row["path"]),
            "aliases": parsed.aliases,
            "tags": parsed.tags,
            "summary": parsed.summary,
            "body": parsed.body,
            "sha256": sha,
            "mtime_ns": row["mtime_ns"],
            "lines": text.count("\n") + (0 if text.endswith("\n") or not text else 1),
        }
        if parsed.load == LOAD_ALWAYS:
            payload["load"] = LOAD_ALWAYS
        for kind in _LINEAGE_KINDS:
            targets = self.lineage_targets(address, kind)
            if targets:
                payload[kind] = targets
        extra = {k: v for k, v in parsed.frontmatter.items() if k not in KNOWN_FIELDS}
        if extra:
            payload["meta"] = extra
        unresolved = self.unresolved_refs(address)
        if unresolved:
            payload["unresolved_refs"] = unresolved
        if parsed.errors:
            payload["parse_errors"] = parsed.errors
        return payload


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------


def search(
    ws: "Workspace",
    query: str,
    source: str | Sequence[str] | None = None,
    tags: str | Sequence[str] | None = None,
    k: int = 10,
    offset: int = 0,
    max_neighbors: int = 3,
    follow_supersedes: FollowSpec = True,
) -> dict[str, Any]:
    _nonneg(k=k, offset=offset, max_neighbors=max_neighbors)
    sources = [normalize_alias(s) for s in _as_str_list(source)] or None
    tag_list = [t for t in _as_str_list(tags) if t.strip()]
    with ws._reading() as table:
        known = {m.alias for m in table.all()}
        unknown = [s for s in sources or [] if s not in known]
        if unknown:
            raise NotFoundError(f"unknown mount(s): {', '.join(unknown)}", mounts=unknown)
        ctx = _Ctx(ws, table, follow_supersedes)
        idx = ctx.idx

        def eligible(address: str) -> bool:
            row = ctx.row(address)
            if row is None or row["is_overview"]:
                return False
            if sources and row["mount"] not in sources:
                return False
            return idx.card_has_tags(row["mount"], row["path"], tag_list)

        # Superseded hits are routes to their replacement; deduplicated groups keep the best
        # value of each ranking signal (design: max(score(A), score(B))).
        groups: dict[str, dict[str, Any]] = {}
        hits = idx.search(query, sources, tag_list)
        for hit in hits:
            address = ctx.remember(hit.row)
            fwd = ctx.lv.forward(address)
            target, via = address, None
            if fwd.redirected and eligible(fwd.node):
                target, via = fwd.node, address
            group = groups.setdefault(target, {"score": hit.score, "coverage": hit.coverage, "phrases": hit.phrases, "via": []})
            group["score"] = max(group["score"], hit.score)
            group["coverage"] = max(group["coverage"], hit.coverage)
            group["phrases"] = max(group["phrases"], hit.phrases)
            if via and via not in group["via"]:
                group["via"].append(via)

        ordered = sorted(groups.items(), key=lambda item: result_order(item[0], item[1], ctx.row(item[0])))
        total = len(ordered)
        results = [
            _preview(ctx, address, group, max_neighbors)
            for address, group in ordered[offset : offset + k]
        ]
        return {
            "query": query,
            "results": results,
            "total_matches": total,
            "offset": offset,
            "k": k,
            "truncated": offset + k < total,
            "next_offset": _page(total, offset, k),
            # About the query, not the results: words no card in scope contains (changes nothing above).
            "unmatched_terms": idx.unmatched_terms(query, hits),
        }


def result_order(address: str, group: dict[str, Any], row) -> tuple:
    """Order of search results: BM25 score (the best of a redirected group), precedence, address."""
    return (-group["score"], -row["precedence"], address)


def _preview(ctx: _Ctx, address: str, group: dict[str, Any], max_neighbors: int) -> dict[str, Any]:
    row = ctx.row(address)
    via = group["via"]
    summary, cut = truncate(_collapse(row["preview"]), SUMMARY_PREVIEW_CHARS)
    out: dict[str, Any] = {
        "address": address,
        "role": row["role"],
        "precedence": row["precedence"],
        "mtime_ns": row["mtime_ns"],
        "score": round(float(group["score"]), 6),
        "coverage": round(float(group["coverage"]), 3),
        "title": row["title"],
        "tags": json.loads(row["tags"]),
        "summary": summary,
    }
    if cut:
        out["summary_truncated"] = True
    if row["load"] == LOAD_ALWAYS:
        out["load"] = LOAD_ALWAYS
    out.update(ctx.status(address))
    fwd = ctx.lv.forward(address)
    if fwd.redirected:
        out["resolves_to"] = fwd.node
    if via:
        out["matched_via_superseded"] = via
        bypassed = ctx.bypassed_replacements(*via)
        if bypassed:
            out["bypassed_replacements"] = bypassed
    for kind in _LINEAGE_KINDS:
        targets = ctx.lineage_targets(address, kind)
        if targets:
            out[kind] = targets
    # Same notices as read(), over the whole extends closure: a superseded or deleted baseline of
    # a baseline undermines this card too.
    baselines, missing = _baseline_closure(ctx, address)
    replaced = []
    for base in baselines:
        for r in ctx.lv.all_superseders(base):
            if r not in replaced:
                replaced.append(r)
    if replaced:
        out["baseline_superseded_by"] = replaced
    if missing:
        out["missing_baselines"] = missing
    neighbors = _neighbors(ctx, address)
    out["neighbors"] = [ctx.brief(a) | {"direction": d} for a, d in neighbors[:max_neighbors]]
    out["total_neighbors"] = len(neighbors)
    out["neighbors_truncated"] = len(neighbors) > max_neighbors
    return out


def _neighbors(ctx: _Ctx, address: str) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for link in ctx.outbound(address):
        if link["kind"] == "wikilink" and link["resolved"]:
            target = format_address(link["dst_mount"], link["dst_path"])
            if target != address:
                seen.setdefault(target, "out")
    mount, path = _split(address)
    for r in ctx.idx.inbound("wikilink", mount, path):
        src = format_address(r["src_mount"], r["src_path"])
        seen.setdefault(src, "in")
    return list(seen.items())


# ---------------------------------------------------------------------------
# read()
# ---------------------------------------------------------------------------


def _select(ctx: _Ctx, address: str) -> tuple[str, list[str]]:
    """Step 1 of section 4.2: initial node selection (+ shadows for unqualified paths)."""
    alias, path = parse_address(address)
    idx = ctx.idx
    if alias is not None:
        if ctx.table.get(alias) is None:
            raise NotFoundError(f"unknown mount {alias}", address=address)
        row = idx.card(alias, path)
        if row is None:
            rows = idx.cards_with_alias(path, mount=alias)
            row = rows[0] if rows else None
        if row is None:
            raise NotFoundError(f"no card {path!r} in {alias}", address=address)
        return ctx.remember(row), []
    rows = idx.cards_at_path(path)
    if not rows:
        rows = idx.cards_with_alias(path)
        if not rows:
            raise NotFoundError(f"no card {path!r} in any mount", address=address)
        return ctx.remember(rows[0]), []
    selected = ctx.remember(rows[0])
    # Same-path cards connected to the selection by a direct extends/supersedes edge (either
    # direction) are lineage, not shadows.
    linked = set()
    for kind in _LINEAGE_KINDS:
        linked.update(ctx.lineage_targets(selected, kind))
        linked.update(format_address(r["src_mount"], r["src_path"]) for r in idx.inbound(kind, *_split(selected)))
    shadows = [other for other in (ctx.remember(r) for r in rows[1:]) if other not in linked]
    return selected, shadows


def _baseline_closure(ctx: _Ctx, start: str) -> tuple[list[str], list[dict[str, str]]]:
    order: list[str] = []
    missing: list[dict[str, str]] = []
    seen = {start}

    def visit(address: str, depth: int) -> None:
        if depth > 64:
            return
        for link in ctx.outbound(address):
            if link["kind"] != "extends":
                continue
            if not link["resolved"]:
                missing.append({"source": address, "ref": link["raw"]})
                continue
            base = format_address(link["dst_mount"], link["dst_path"])
            if base in seen:
                continue
            seen.add(base)
            visit(base, depth + 1)
            order.append(base)

    visit(start, 0)
    return order, missing


def read(
    ws: "Workspace",
    address: str,
    follow_supersedes: FollowSpec = True,
    max_backlinks: int = 10,
    backlinks_offset: int = 0,
    max_extensions: int = 5,
    extensions_offset: int = 0,
) -> dict[str, Any]:
    _nonneg(
        max_backlinks=max_backlinks,
        backlinks_offset=backlinks_offset,
        max_extensions=max_extensions,
        extensions_offset=extensions_offset,
    )
    with ws._reading() as table:
        ctx = _Ctx(ws, table, follow_supersedes)
        return resolve(ctx, address, max_backlinks, backlinks_offset, max_extensions, extensions_offset)


def resolve(
    ctx: _Ctx,
    address: str,
    max_backlinks: int = 10,
    backlinks_offset: int = 0,
    max_extensions: int = 5,
    extensions_offset: int = 0,
    bump_telemetry: bool = True,
) -> dict[str, Any]:
    """The body of ``read()`` for a caller that already holds the workspace lock."""
    idx = ctx.idx
    selected, shadows = _select(ctx, address)

    # Step 2: transitive supersession forwarding (filtered by trust policy).
    fwd = ctx.lv.forward(selected)
    node = fwd.node
    result = ctx.card_payload(node)
    result["requested"] = address
    result.update(ctx.status(node))
    if fwd.redirected:
        result["redirected_from"] = selected
        result["lineage_path"] = fwd.path
        bypassed = ctx.bypassed_replacements(selected)
        if bypassed:
            result["bypassed_replacements"] = bypassed
    if shadows:
        result["shadows"] = shadows

    # Extensions of superseded nodes are never silently rebased onto the replacement.
    if fwd.redirected:
        unrebased = []
        for old in sorted(fwd.superseded):
            for r in idx.inbound("extends", *_split(old)):
                ext = format_address(r["src_mount"], r["src_path"])
                if ext == node or node in ctx.lineage_targets(ext, "extends"):
                    continue
                unrebased.append({"address": ext, "extends": old})
        if unrebased:
            result["unrebased_extensions"] = unrebased

    # Step 3: extension composition.
    baselines, missing = _baseline_closure(ctx, node)
    if baselines:
        composed = []
        replaced: list[str] = []
        for base in baselines:
            payload = ctx.card_payload(base)
            direct = ctx.lv.all_superseders(base)
            if direct:
                payload["superseded_by"] = direct
                replaced += [r for r in direct if r not in replaced]
            composed.append(payload)
        result["baselines"] = composed
        if replaced:
            result["baseline_superseded_by"] = replaced
    if missing:
        result["missing_baselines"] = missing

    ext_rows = idx.inbound("extends", *_split(node), recency=True)
    if ext_rows:
        page = ext_rows[extensions_offset : extensions_offset + max_extensions]
        result["extensions"] = [ctx.card_payload(format_address(r["src_mount"], r["src_path"])) for r in page]
        result["total_extensions"] = len(ext_rows)
        result["extensions_next_offset"] = _page(len(ext_rows), extensions_offset, max_extensions)

    # Outbound wikilinks + paginated backlinks.
    links = [
        {"ref": l["raw"], "address": format_address(l["dst_mount"], l["dst_path"]) if l["resolved"] else None}
        for l in ctx.outbound(node)
        if l["kind"] == "wikilink"
    ]
    if links:
        result["links"] = links
    back_rows = idx.inbound("wikilink", *_split(node))
    result["backlinks"] = [
        {"address": a, "title": (ctx.row(a)["title"] if ctx.row(a) is not None else None)}
        for a in (format_address(r["src_mount"], r["src_path"]) for r in back_rows[backlinks_offset : backlinks_offset + max_backlinks])
    ]
    result["total_backlinks"] = len(back_rows)
    result["backlinks_next_offset"] = _page(len(back_rows), backlinks_offset, max_backlinks)

    telemetry = idx.bump_read(result["mount"], result["path"]) if bump_telemetry else None
    if telemetry is not None:
        result["read_count"], result["last_read_at"] = telemetry
    return result
