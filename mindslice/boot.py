"""Always-loaded cards (``load = "always"``): the boot set, its rendering, and its write protection.

A card whose frontmatter says ``load = "always"`` holds session-level context: an agent persona, the
user's language, standing instructions. Every session reads it at start (MCP ``initialize``
instructions, ``manifest()``, ``mindslice boot``), whether or not a query would have found it.
Otherwise it is an ordinary card: searchable, readable, and subject to lineage like any other.

The boot set is each always-loaded card resolved as ``read()`` resolves it: a superseded card
forwards to its replacement, and baselines and extensions are composed in. Its *footprint* is
every card whose content (or lineage) decides what the set contains. Because those cards shape
every session, a write that touches the footprint is staged for the user's approval by default
(``write(stage=None)``), and ``apply()`` is that approval.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Iterable

from . import query
from .addressing import format_address, resolve_ref
from .card import LOAD_ALWAYS, parse_card

if TYPE_CHECKING:  # pragma: no cover
    from .config import MountTable
    from .workspace import Workspace

# Extensions composed into one boot card (read() pages them; the boot set shows them all up to this).
MAX_EXTENSIONS = 50

HEADER = (
    "# Always-loaded memory\n\n"
    "These cards come from the user's MindSlice memory and apply to the whole session (persona, language, "
    "standing instructions). Follow them unless the user says otherwise. Changes to them are staged for the "
    "user's approval."
)


def _card(c: dict[str, Any]) -> dict[str, Any]:
    return {"address": c["address"], "title": c["title"], "summary": c.get("summary", ""), "body": c.get("body", "")}


def collect(ctx: "query._Ctx") -> tuple[list[dict[str, Any]], set[str]]:
    """``(entries, footprint)``: the rendered boot cards and every address that shapes them."""
    entries: list[dict[str, Any]] = []
    footprint: set[str] = set()
    shown: set[str] = set()
    for row in ctx.idx.always_cards():
        address = format_address(row["mount"], row["path"])
        r = query.resolve(ctx, address, max_backlinks=0, max_extensions=MAX_EXTENSIONS, bump_telemetry=False)
        baselines = r.get("baselines", [])
        extensions = r.get("extensions", [])
        parts = [r["address"], *(b["address"] for b in baselines), *(e["address"] for e in extensions)]
        footprint.update([address, *r.get("lineage_path", []), *parts])
        if all(a in shown for a in parts):
            continue  # everything it would show is already in the set (e.g. an always-loaded extension)
        shown.update(parts)
        entry = _card(r) | {"mount": r["mount"], "role": r["role"], "sha256": r["sha256"]}
        if r.get("redirected_from"):
            entry["redirected_from"] = r["redirected_from"]
        if r.get("status") != "active":
            entry["status"] = r["status"]
        if baselines:
            entry["baselines"] = [_card(b) for b in baselines]
        if extensions:
            entry["extensions"] = [_card(e) for e in extensions]
            if r.get("total_extensions", 0) > len(extensions):
                entry["total_extensions"] = r["total_extensions"]
        entries.append(entry)
    return entries, footprint


def pending_approval(ws: "Workspace") -> list[dict[str, Any]]:
    out = []
    for path, entry in ws.staging.entries().items():
        reason = entry.get("requires_approval")
        if reason:
            out.append({"id": path, "op": entry.get("op", "write"), "reason": reason})
    return out


def is_empty_workspace(ws: "Workspace", table: "MountTable") -> bool:
    """True when only ``@overlay`` is mounted, no cards are indexed, and nothing is staged."""
    if len(table.all()) > 1 or ws.staging.entries():
        return False
    return ws.index.conn.execute("SELECT 1 FROM cards LIMIT 1").fetchone() is None


def snapshot(ws: "Workspace", table: "MountTable") -> dict[str, Any]:
    """The boot set for a caller that already holds the workspace lock."""
    entries, _ = collect(query._Ctx(ws, table, True))
    out: dict[str, Any] = {"cards": entries, "total": len(entries)}
    pending = pending_approval(ws)
    if pending:
        out["pending_approval"] = pending
    if not entries and is_empty_workspace(ws, table):
        out["empty_workspace"] = True
    return out


def boot(ws: "Workspace") -> dict[str, Any]:
    with ws._reading() as table:
        return snapshot(ws, table)


def fingerprint(entry: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def render_markdown(cards: Iterable[dict[str, Any]], header: str = HEADER) -> str:
    """The boot cards as one Markdown block, ready for a system prompt. Empty when there are none."""
    out: list[str] = []

    def block(c: dict[str, Any], heading: str) -> None:
        out.append(f"{heading} {c['title']} ({c['address']})")
        for part in (c.get("summary", ""), c.get("body", "")):
            if part.strip():
                out.append("")
                out.append(part.strip())
        out.append("")

    for c in cards:
        for base in c.get("baselines", []):
            block(base, "## Baseline:")
        block(c, "##")
        for ext in c.get("extensions", []):
            block(ext, "### Extension:")
    if not out:
        return ""
    prefix = header.rstrip() + "\n\n" if header.strip() else ""
    return prefix + "\n".join(out).rstrip() + "\n"


def protection_reason(
    ws: "Workspace",
    table: "MountTable",
    path: str,
    texts: Iterable[str | None],
    load: str | None,
    lineage: Iterable[tuple[str, str]],
) -> str | None:
    """Why a write to ``@overlay/<path>`` changes the always-loaded context (None if it does not).

    ``texts`` are the card's current versions (overlay and staged), ``load`` and ``lineage`` the
    write's own ``load`` argument and ``extends`` / ``supersedes`` references (named by kind in
    ``lineage``: ``[("extends", ref), ...]``).
    """
    overlay = table.overlay
    address = format_address(overlay.alias, path)
    if load == LOAD_ALWAYS:
        return f"it makes {address} always-loaded"
    parsed = [parse_card(t) for t in texts if t is not None]
    if any(p.load == LOAD_ALWAYS for p in parsed):
        return f"{address} is always-loaded"
    ctx = query._Ctx(ws, table, True)
    _, footprint = collect(ctx)
    if not footprint:
        return None
    if address in footprint:
        return f"{address} is part of the always-loaded context"
    cats = ws.index.catalogs()
    refs = list(lineage)
    for p in parsed:
        refs += [("extends", raw) for raw in p.extends] + [("supersedes", raw) for raw in p.supersedes]
    for verb, raw in refs:
        res = resolve_ref(raw, overlay.alias, cats)
        if res.resolved and res.address in footprint:
            return f"it {verb} {res.address}, which is part of the always-loaded context"
    return None


__all__ = [
    "boot",
    "snapshot",
    "collect",
    "is_empty_workspace",
    "render_markdown",
    "protection_reason",
    "pending_approval",
    "fingerprint",
    "HEADER",
]
