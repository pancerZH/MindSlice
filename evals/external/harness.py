"""Build one workspace per haystack, ingest it, ask its questions, and record what search() returned.

Mode A builds a flat corpus (no lineage) in one bulk ingestion, unless questions must be asked part-way
(MEME's ``before_questions``), in which case sessions are ingested in order and each question is asked
right after its session. Mode B (``lineage=True``) always ingests in order: cards with no lineage are
written as files session by session, and every lineage operation goes through ``Workspace.write``
(``create`` with ``supersedes`` / ``extends``, or ``op="delete"``), as an agent recording memory would.

Each record holds the first page (``k = 10``), per-result lineage markers, ``coverage`` and
``unmatched_terms``. A record whose page holds no judged card also gets the judged cards' best rank in
the full ranking (``Index.search``, the same order as ``search()`` for a flat single-mount corpus).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mindslice import NotFoundError, Workspace
from mindslice.retrieval.lexical import analyze_query

from .corpus import GRANULARITY, Card, add_files, address, new_workspace, write_card
from .datasets import Haystack, Question

K = 10


@dataclass
class Built:
    """A haystack's cards and how judgments map onto them."""

    cards: list[Card]
    card_of_unit: dict[str, Card]
    card_of_address: dict[str, Card]

    def addresses(self, units) -> list[str]:
        return list(dict.fromkeys(address(self.card_of_unit[u]) for u in units if u in self.card_of_unit))


def built(h: Haystack, granularity: str) -> Built:
    cards = GRANULARITY[granularity](h.sessions)
    return Built(cards, {u: c for c in cards for u in c.units}, {address(c): c for c in cards})


def _session_index(card: Card, h: Haystack) -> int:
    return int(card.path.split("/")[0][1:])


def _apply_lineage(h: Haystack, b: Built) -> tuple[dict[str, list[str]], set[str]]:
    """Per card path: lineage fields to add; and the set of card paths that are delete requests."""
    lin = h.lineage
    deletes: dict[str, list[str]] = {}
    for c in b.cards:
        sup = [address(b.card_of_unit[u]) for x in c.units for u in lin.supersedes.get(x, []) if u in b.card_of_unit]
        ext = [address(b.card_of_unit[u]) for x in c.units for u in lin.extends.get(x, []) if u in b.card_of_unit]
        c.supersedes = list(dict.fromkeys(a for a in sup if a != address(c)))
        c.extends = list(dict.fromkeys(a for a in ext if a != address(c)))
        dels = [b.card_of_unit[u].path for x in c.units for u in lin.deletes.get(x, []) if u in b.card_of_unit]
        if any(x in lin.deletes for x in c.units):
            deletes[c.path] = list(dict.fromkeys(dels))
    return deletes, set(deletes)


def run_haystack(h: Haystack, granularity: str, lineage: bool, tmp: Path,
                 after_ingest=None) -> tuple[list[dict[str, Any]], Built, Any]:
    b = built(h, granularity)
    deletes: dict[str, list[str]] = {}
    if lineage:
        deletes, _ = _apply_lineage(h, b)
    ws = new_workspace(tmp / "ws")
    records: list[dict[str, Any]] = []
    extra = None
    try:
        staged = any(q.at_session is not None for q in h.questions)
        if not lineage and not staged:
            add_files(ws, b.cards)
            records += [ask(ws, h, q, b, granularity, lineage) for q in h.questions]
        else:
            by_session: dict[int, list[Card]] = {}
            for c in b.cards:
                by_session.setdefault(_session_index(c, h), []).append(c)
            asked: set[str] = set()
            for i in range(len(h.sessions)):
                cards = by_session.get(i, [])
                plain = [c for c in cards if not (c.supersedes or c.extends or c.path in deletes)]
                add_files(ws, plain)
                for c in cards:
                    if c.path in deletes:
                        for target in deletes[c.path]:
                            ws.write(target, op="delete")
                    elif c.supersedes or c.extends:
                        write_card(ws, c)
                for q in h.questions:
                    if q.at_session == i:
                        records.append(ask(ws, h, q, b, granularity, lineage))
                        asked.add(q.id)
            records += [ask(ws, h, q, b, granularity, lineage) for q in h.questions if q.id not in asked]
        if after_ingest is not None:
            extra = after_ingest(ws, h, b, deletes, records)
    finally:
        ws.close()
    return records, b, extra


def run_in_tmp(h: Haystack, granularity: str, lineage: bool, after_ingest=None):
    with tempfile.TemporaryDirectory(prefix="mindslice-ext-") as tmp:
        return run_haystack(h, granularity, lineage, Path(tmp), after_ingest)


def ask(ws: Workspace, h: Haystack, q: Question, b: Built, granularity: str, lineage: bool) -> dict[str, Any]:
    res = ws.search(q.text, k=K)
    results = res["results"]
    ranked = [r["address"] for r in results]
    plan = analyze_query(q.text)
    n_units = len(plan.units)
    rec: dict[str, Any] = {
        "dataset": h.dataset, "haystack": h.key, "id": q.id, "category": q.category,
        "granularity": granularity, "variant": "lineage" if lineage else "flat",
        "answerable": q.answerable, "query": q.text, "ranked": ranked,
        "sessions": [b.card_of_address[a].session for a in ranked],
        # A preview warns when the card is superseded or its extends chain changed: a baseline replaced
        # (baseline_superseded_by) or deleted (missing_baselines), the two signals read() gives (PLAN.md, ac7928a).
        "warned": [r["status"] != "active" or _basis_changed(r) for r in results],
        "baseline_flagged": [_basis_changed(r) for r in results],
        "via": [r.get("matched_via_superseded", []) for r in results],
        "scores": [r["score"] for r in results],
        "coverage_max": max((r["coverage"] for r in results), default=0.0),
        "coverage_top1": results[0]["coverage"] if results else 0.0,
        "unmatched_terms": res["unmatched_terms"],
        "unmatched_share": (len(res["unmatched_terms"]) / n_units) if n_units else 1.0,
        "total_matches": res["total_matches"],
        "gold": b.addresses(q.gold),
        "gold_sessions": sorted(q.gold_sessions),
    }
    for key in ("current", "stale", "history", "request"):
        if key in q.meta:
            rec[key] = b.addresses(q.meta[key])
    if "deleted_values" in q.meta:
        rec["value_leak"] = _leaks(ws, ranked, q.meta["deleted_values"], set(b.addresses(q.meta.get("request", []))))
    for key in ("task", "phase", "hop"):
        if key in q.meta:
            rec[key] = q.meta[key]
    if rec["gold"] and not set(rec["gold"]) & set(ranked) and not lineage:
        rec["gold_rank"] = _best_rank(ws, q.text, set(rec["gold"]))
        rec["miss_words"] = _miss_words(ws, q.text, rec["gold"])
    return rec


def _basis_changed(result: dict[str, Any]) -> bool:
    return bool(result.get("baseline_superseded_by") or result.get("missing_baselines"))


def _leaks(ws: Workspace, ranked: list[str], values: list[str], requests: set[str]) -> bool:
    """Some result other than the delete request itself still states a deleted value."""
    for a in ranked:
        if a in requests:
            continue
        card = ws.read(a, follow_supersedes=False)
        text = (card["summary"] + "\n" + card["body"]).casefold()
        if any(v.casefold() in text for v in values):
            return True
    return False


def _best_rank(ws: Workspace, query: str, gold: set[str]) -> int | None:
    """1-based rank of the best judged card in the full ranking; None if no judged card matches at all."""
    for i, hit in enumerate(ws.index.search(query)):
        if f"{hit.row['mount']}/{hit.row['path']}" in gold:
            return i + 1
    return None


def _miss_words(ws: Workspace, query: str, gold: list[str]) -> list[dict[str, Any]]:
    """For a first-page miss: each query word, the share of the haystack's cards containing it, and
    whether some judged card contains it (diagnostics for the report; changes nothing)."""
    idx = ws.index
    n = idx.conn.execute("SELECT COUNT(*) FROM cards WHERE is_overview = 0").fetchone()[0] or 1
    gold_ids = {row["id"] for row in (idx.card(*a.split("/", 1)) for a in gold) if row is not None}
    out = []
    for unit in analyze_query(query).units:
        ids: set[int] = set()
        for term in unit.terms:
            ids |= idx._matching_ids(term)
        out.append({"word": unit.text, "df": round(len(ids) / n, 4), "in_gold": bool(ids & gold_ids)})
    return out


def read_or_none(ws: Workspace, addr: str, **kw) -> dict[str, Any] | None:
    try:
        return ws.read(addr, **kw)
    except NotFoundError:
        return None
