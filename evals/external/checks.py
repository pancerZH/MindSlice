"""Mode B structural checks: with lineage compiled from the annotations, do read() and search() expose it?

Run after a lineage haystack is fully ingested (its after-change questions already asked). Each check is
a plain yes/no about a response field, against what the compiled lineage implies:

* ``root-forwarding``: ``read(old root value)`` lands on the change card (``redirected_from`` set).
* ``root-unrebased``: that read lists exactly the cards extending the old value in ``unrebased_extensions``.
* ``dependent-flagged``: ``read(dependent's value card)`` names the root change in ``baseline_superseded_by``
  (through the ``extends`` closure, so 2-hop dependents count), or reports ``missing_baselines`` when a card
  on its chain was deleted (MEME ``sw_019``, ``sw_037``).
* ``rule-attached`` (Cascade): the dependent's if-then rule cards are in its ``extensions``.
* ``deleted-unreadable``: a deleted card raises ``not_found``; ``dependent-of-deleted-flagged``: a card
  extending it reports ``missing_baselines``.
* ``history-chain`` (Tracking): following ``supersedes`` back from the latest value (``follow_supersedes=False``)
  yields the full history in order; ``history-forwarding``: ``read(first value)`` lands on the latest with
  that ``lineage_path``.
* ``stale-forwarding`` (LongMemEval knowledge updates, MemoryAgentBench conflicts): ``read(stale card)``
  lands on the card that supersedes it.

End-to-end rows (``e2e``) start from the question's first search page instead of a known address, as an
agent would: find the dependent's value or rule card there, read it, and check the same signals.
"""

from __future__ import annotations

from typing import Any

from mindslice import Workspace

from .corpus import address
from .datasets import Haystack
from .harness import Built, read_or_none


def _row(h: Haystack, check: str, subject: str, ok: bool, **detail: Any) -> dict[str, Any]:
    return {"dataset": h.dataset, "haystack": h.key, "check": check, "subject": subject, "ok": bool(ok), **detail}


def meme(ws: Workspace, h: Haystack, b: Built, deletes: dict[str, list[str]], records: list[dict]) -> list[dict]:
    facts = h.info["facts"]
    deleted = {f"@overlay/{p}" for ps in deletes.values() for p in ps}

    def cards(entity: str, kind: str) -> list[str]:
        out = [address(b.card_of_unit[f["unit"]]) for f in facts.get(entity, []) if f["kind"] == kind]
        return [a for a in out if a not in deleted]

    rows: list[dict] = []
    root_values = cards(h.info["root"], "value")
    change = root_values[-1] if len(root_values) >= 2 else None
    if change:
        intro = root_values[0]
        r = ws.read(intro, max_extensions=100)
        rows.append(_row(h, "root-forwarding", intro, r["address"] == change and r.get("redirected_from") == intro))
        expected = {address(c) for c in b.cards if intro in c.extends and address(c) not in deleted}
        got = {x["address"] for x in r.get("unrebased_extensions", [])}
        rows.append(_row(h, "root-unrebased", intro, got == expected, expected=len(expected), got=len(got)))

    by_id = {rec["id"]: rec for rec in records}
    for q in h.questions:
        task, phase = q.meta.get("task"), q.meta.get("phase")
        if phase != "after":
            continue
        target = q.meta["entities"][0]
        if task in ("Cas", "Abs"):
            values, rules = cards(target, "value"), cards(target, "rule")
            if not values or change is None:
                continue
            hop = f"{task}-hop{q.meta['hop']}"
            r = ws.read(values[-1], max_extensions=100)
            signal = _flag(r, change)
            ext = {e["address"] for e in r.get("extensions", [])}
            rows.append(_row(h, "dependent-flagged", q.id, signal is not None, group=hop, signal=signal))
            if task == "Cas":
                rows.append(_row(h, "rule-attached", q.id, bool(rules) and set(rules) <= ext, group=hop))
            else:
                rows.append(_row(h, "no-rule", q.id, not rules and not (ext & set(rules)), group=hop))
            rows.append(_e2e(ws, h, q.id, hop, by_id.get(q.id), values, rules, change))
        elif task == "Tr":
            history = [address(b.card_of_unit[f["unit"]]) for f in facts.get(target, []) if f["kind"] == "value"]
            if len(history) < 2:
                continue
            chain, cur = [history[-1]], history[-1]
            while True:
                sup = ws.read(cur, follow_supersedes=False).get("supersedes", [])
                if not sup or sup[0] in chain:
                    break
                cur = sup[0]
                chain.append(cur)
            rows.append(_row(h, "history-chain", q.id, chain[::-1] == history, length=len(history)))
            r = ws.read(history[0])
            rows.append(_row(h, "history-forwarding", q.id,
                             r["address"] == history[-1] and r.get("lineage_path") == history))
    for path_list in deletes.values():
        for p in path_list:
            a = f"@overlay/{p}"
            rows.append(_row(h, "deleted-unreadable", a, read_or_none(ws, a) is None))
            for c in b.cards:
                if a in c.extends and address(c) not in deleted:
                    r = ws.read(address(c), follow_supersedes=False)
                    rows.append(_row(h, "dependent-of-deleted-flagged", address(c), bool(r.get("missing_baselines"))))
    # Only searches made after the deletions (before-change questions ran while the cards still existed).
    seen_deleted = sum(1 for rec in records if rec.get("phase") == "after" for x in rec["ranked"] if x in deleted)
    rows.append(_row(h, "deleted-never-returned", h.key, seen_deleted == 0, returned=seen_deleted))
    return rows


def _flag(r: dict, change: str) -> str | None:
    """How a read dependent signals that its basis is gone: the root change named in
    ``baseline_superseded_by``, or (when a baseline on its chain was deleted) ``missing_baselines``."""
    if change in r.get("baseline_superseded_by", []):
        return "baseline_superseded_by"
    if r.get("missing_baselines"):
        return "missing_baselines"
    return None


def _e2e(ws: Workspace, h: Haystack, qid: str, group: str, rec: dict | None, values: list[str], rules: list[str],
         change: str) -> dict:
    """From the first search page: is the dependent there, flagged in its preview, flagged once read, and
    (Cascade) is its replacement rule reachable?"""
    wanted = set(values) | set(rules)
    ranked = rec["ranked"] if rec else []
    hits = [i for i, a in enumerate(ranked) if a in wanted]
    found = bool(hits)
    preview = any(rec["baseline_flagged"][i] for i in hits) if found else False
    read_flag = rule_ok = False
    if found:
        r = ws.read(ranked[hits[0]], max_extensions=100)
        read_flag = _flag(r, change) is not None
        ext = {e["address"] for e in r.get("extensions", [])}
        reachable = set(a for a in ranked) | ext | {r["address"]}
        rule_ok = bool(rules) and bool(set(rules) & reachable)
    ok = found and read_flag and (rule_ok if group.startswith("Cas") else True)
    return _row(h, "e2e", qid, ok, group=group, found=found, preview_flag=preview, read_flag=read_flag,
                rule_reachable=rule_ok)


def stale_forwarding(ws: Workspace, h: Haystack, b: Built, deletes, records) -> list[dict]:
    rows = []
    replacement = {s: address(c) for c in b.cards for s in c.supersedes}
    for rec in records:
        for s in rec.get("stale", []):
            if s in replacement:
                r = ws.read(s)
                rows.append(_row(h, "stale-forwarding", rec["id"],
                                 r["address"] == replacement[s] and r.get("redirected_from") == s))
    return rows


CHECKS = {"meme-filler32k": meme, "meme-nofiller": meme, "longmemeval-s": stale_forwarding, "mab-sh": stale_forwarding}
