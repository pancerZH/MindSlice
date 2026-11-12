"""Inbound impact of retiring a card: who still links to it or extends it.

When ``write()`` supersedes or deletes a card, the cards that ``[[link]]`` to it or ``extends`` it keep
pointing at the old card: a link whose target names an old value keeps stating that value, and an
extension keeps resting on a premise that changed. This module lists them, straight from the index
(plus staged overrides for ``stage=True``), so the caller can update or rebase them. It is pure
mechanism: no ranking, no judgment about which ones matter. Results are ordered by mount precedence,
then address, then target, and bounded by ``MAX_AFFECTED`` per list (totals are always reported).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from ..model.addressing import MountCatalog, format_address, resolve_ref

if TYPE_CHECKING:  # pragma: no cover
    from ..model.card import ParsedCard
    from ..retrieval.index import Index

MAX_AFFECTED = 25
_KINDS = (("wikilink", "affected_backlinks", "links_to"), ("extends", "affected_extensions", "extends"))


def _split(address: str) -> tuple[str, str]:
    mount, _, path = address.partition("/")
    return mount, path


def supersede_targets(parsed: "ParsedCard", src_mount: str, cats: dict[str, MountCatalog]) -> list[str]:
    """Resolved addresses of the cards ``parsed`` supersedes, in order, without duplicates."""
    out: list[str] = []
    for raw in parsed.supersedes:
        res = resolve_ref(raw, src_mount, cats)
        if res.resolved and res.address and res.address not in out:
            out.append(res.address)
    return out


def inbound_impact(
    index: "Index",
    overlay_alias: str,
    overlay_precedence: int,
    targets: Iterable[str],
    *,
    overrides: dict[str, "ParsedCard | None"] | None = None,
    cats: dict[str, MountCatalog] | None = None,
    exclude: Iterable[str] = (),
    dangling: bool = False,
) -> dict[str, Any]:
    """``affected_backlinks`` / ``affected_extensions`` (+ totals) for cards that reference ``targets``.

    ``overrides`` are staged overlay cards (path -> parsed card, None for a staged delete): indexed
    links from those paths are replaced by the staged versions' own references, resolved with
    ``cats``. ``exclude`` drops sources (the card being written). ``dangling=True`` matches references
    that name a target by path but no longer resolve (the target was already deleted).
    """
    targets = list(dict.fromkeys(targets))
    overrides = overrides or {}
    skip = set(exclude) | set(targets)
    found: dict[str, dict[tuple[str, str], int]] = {kind: {} for kind, _, _ in _KINDS}
    for target in targets:
        mount, path = _split(target)
        for kind, _, _ in _KINDS:
            rows = index.dangling_inbound(kind, mount, path) if dangling else index.inbound(kind, mount, path)
            for r in rows:
                if r["src_mount"] == overlay_alias and r["src_path"] in overrides:
                    continue  # superseded by its staged version, handled below
                src = format_address(r["src_mount"], r["src_path"])
                if src not in skip:
                    found[kind][(src, target)] = r["precedence"]
    if overrides and cats is not None:
        wanted = set(targets)
        for path, parsed in overrides.items():
            src = format_address(overlay_alias, path)
            if parsed is None or src in skip:
                continue
            refs = {"wikilink": parsed.wikilink_targets(), "extends": parsed.extends}
            for kind, raws in refs.items():
                for raw in raws:
                    res = resolve_ref(raw, overlay_alias, cats)
                    if res.resolved and res.address in wanted:
                        found[kind][(src, res.address)] = overlay_precedence
    out: dict[str, Any] = {}
    for kind, key, field in _KINDS:
        ordered = sorted(found[kind].items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1]))
        items = []
        for (src, target), _ in ordered[:MAX_AFFECTED]:
            item: dict[str, Any] = {"address": src, field: target}
            if _split(src)[0] != overlay_alias:
                item["read_only"] = True
            items.append(item)
        out[key] = items
        out["total_" + key] = len(ordered)
    return out


__all__ = ["MAX_AFFECTED", "inbound_impact", "supersede_targets"]
