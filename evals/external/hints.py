"""Mode C (PLAN.md): could the engine name the card a new write supersedes?

Replays Mode B ingestion and, just before chosen writes, calls ``search()`` with the card's own text, the
way a ``write()`` implementation could. No engine change and no LLM: this measures whether a lexical
candidate list is precise enough to offer an agent. Rules, lines and the selection procedure are fixed in
PLAN.md ("Mode C"); ``dev`` picks the query variant and coverage threshold, ``holdout`` is read once with
that choice.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Sequence

from evals.retrieval.metrics import interval, resamples, verdict

from .corpus import Card, add_files, address, new_workspace, write_card
from .datasets import LOADERS, Haystack
from .harness import _apply_lineage, _session_index, built

DATASETS = ("longmemeval-s", "meme-filler32k", "mab-sh")
GRANULARITY_OF = {"longmemeval-s": "round", "meme-filler32k": "round", "mab-sh": "turn"}  # = run.STATE_GRANULARITY
SAMPLE_MOD = {"longmemeval-s": 8, "meme-filler32k": 5, "mab-sh": 13}  # plain writes kept when hash % m == 0
VARIANTS = ("full", "summary")
THRESHOLDS = tuple(round(0.05 * i, 2) for i in range(20))  # 0.00 .. 0.95
CANDIDATES = 3  # results a hint may name
PROBE_K = 5  # results recorded per probe (R@1, R@3 and the hint use the first 3)
DEV_FIRE_MAX = 0.10
LINES = {"H1": 0.80, "H2a": 0.60, "H2b": 0.20}
_EPS = 1e-9  # coverage is reported rounded to 3 decimals


def _hash(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def split_of(haystack: str, path: str) -> str:
    return "dev" if _hash(f"split/{haystack}/{path}") % 2 == 0 else "holdout"


def sampled(dataset: str, haystack: str, path: str) -> bool:
    return _hash(f"neg/{haystack}/{path}") % SAMPLE_MOD[dataset] == 0


def query_text(card: Card, variant: str) -> str:
    """The card's text as written, minus its title and its ``Date:`` line (harness templates)."""
    if variant == "summary":
        return card.summary
    body = card.body[1:] if card.body and card.body[0].startswith("Date: ") else card.body
    return "\n".join([card.summary, *body])


def _probe(ws, card: Card) -> dict[str, list[dict[str, Any]]]:
    out = {}
    for variant in VARIANTS:
        text = query_text(card, variant)
        # A blank query would list every card (search()'s facet mode): no candidates instead.
        results = ws.search(text, k=PROBE_K)["results"] if text.strip() else []
        out[variant] = [{"address": r["address"], "coverage": r["coverage"], "score": r["score"]} for r in results]
    return out


def probe_haystack(h: Haystack, split: str, tmp: Path) -> list[dict[str, Any]]:
    """Mode B ingestion, in harness order, probing the ``split``'s writes just before they happen."""
    dataset = h.dataset
    b = built(h, GRANULARITY_OF[dataset])
    deletes, _ = _apply_lineage(h, b)
    ws = new_workspace(tmp / "ws")
    out: list[dict[str, Any]] = []

    def record(card: Card, group: str) -> None:
        if split_of(h.key, card.path) != split:
            return
        out.append({"dataset": dataset, "haystack": h.key, "path": card.path, "group": group, "split": split,
                    "predecessors": list(card.supersedes), "baselines": list(card.extends),
                    "probes": _probe(ws, card)})

    try:
        by_session: dict[int, list[Card]] = {}
        for c in b.cards:
            by_session.setdefault(_session_index(c, h), []).append(c)
        for i in range(len(h.sessions)):
            cards = by_session.get(i, [])
            plain = [c for c in cards if not (c.supersedes or c.extends or c.path in deletes)]
            for c in plain:
                if sampled(dataset, h.key, c.path):
                    record(c, "plain")
            add_files(ws, plain)
            for c in cards:
                if c.path in deletes:
                    for target in deletes[c.path]:
                        ws.write(target, op="delete")
                elif c.supersedes or c.extends:
                    record(c, "positive" if c.supersedes else "extends")
                    write_card(ws, c)
    finally:
        ws.close()
    return out


def _job(args: tuple[Haystack, str]) -> list[dict[str, Any]]:
    h, split = args
    with tempfile.TemporaryDirectory(prefix="mindslice-hints-") as tmp:
        return probe_haystack(h, split, Path(tmp))


def has_lineage(h: Haystack) -> bool:
    lin = h.lineage
    return lin is not None and bool(lin.supersedes or lin.extends or lin.deletes)


def run(split: str, workers: int, root: Path | None, log=print) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in DATASETS:
        work = [(h, split) for h in LOADERS[name](root) if has_lineage(h)]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for recs in pool.map(_job, work, chunksize=1):
                records += recs
        log(f"{name}: {len(work)} haystacks probed ({split})")
    records.sort(key=lambda r: (r["dataset"], r["haystack"], r["path"]))
    return records


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def hinted(rec: dict[str, Any], variant: str, t: float) -> list[str]:
    return [c["address"] for c in rec["probes"][variant][:CANDIDATES] if c["coverage"] + _EPS >= t]


def at_k(rec: dict[str, Any], variant: str, k: int) -> float:
    top = {c["address"] for c in rec["probes"][variant][:k]}
    return 1.0 if top & set(rec["predecessors"]) else 0.0


def found(rec: dict[str, Any], variant: str, t: float) -> float:
    return 1.0 if set(hinted(rec, variant, t)) & set(rec["predecessors"]) else 0.0


def fires(rec: dict[str, Any], variant: str, t: float) -> float:
    return 1.0 if hinted(rec, variant, t) else 0.0


def names_baseline(rec: dict[str, Any], variant: str, t: float) -> float:
    return 1.0 if set(hinted(rec, variant, t)) & set(rec["baselines"]) else 0.0


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def groups(records: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"positive": [], "plain": [], "extends": []}
    for r in records:
        out[r["group"]].append(r)
    return out


def grid(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    g = groups(records)
    rows = []
    for variant in VARIANTS:
        for t in THRESHOLDS:
            rows.append({"variant": variant, "t": t,
                         "recall": _mean([found(r, variant, t) for r in g["positive"]]),
                         "fire_plain": _mean([fires(r, variant, t) for r in g["plain"]]),
                         "fire_extends": _mean([fires(r, variant, t) for r in g["extends"]])})
    return rows


def select(dev: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """PLAN.md's rule: highest dev recall with plain fire rate <= 0.10; ties: lower fire, then higher t.
    (A tie on all three between variants keeps the first in VARIANTS order.)"""
    rows = grid(dev)
    ok = [r for r in rows if r["fire_plain"] <= DEV_FIRE_MAX + _EPS]
    g = groups(dev)
    r3 = {v: _mean([at_k(r, v, 3) for r in g["positive"]]) for v in VARIANTS}
    if not ok:
        best_variant = max(VARIANTS, key=lambda v: r3[v])
        return {"qualified": False, "variant": best_variant, "t": None, "dev_r3": r3}
    best = max(ok, key=lambda r: (r["recall"], -r["fire_plain"], r["t"]))
    return {"qualified": True, "variant": best["variant"], "t": best["t"], "dev_recall": best["recall"],
            "dev_fire_plain": best["fire_plain"], "dev_fire_extends": best["fire_extends"], "dev_r3": r3}


def _ci(values: Sequence[float]) -> dict[str, float]:
    mean, low, high = interval(values, resamples(len(values)))
    return {"mean": mean, "low": low, "high": high, "n": len(values)}


def describe(records: Sequence[dict[str, Any]], variant: str, t: float | None) -> dict[str, Any]:
    """Per dataset and pooled: R@1, R@3, and (with a threshold) recall, fire rates, hinted cards per write."""
    out: dict[str, Any] = {}
    by_ds: dict[str, list[dict[str, Any]]] = {"pooled": list(records)}
    for r in records:
        by_ds.setdefault(r["dataset"], []).append(r)
    for name, recs in by_ds.items():
        g = groups(recs)
        row: dict[str, Any] = {"positives": len(g["positive"]), "plain": len(g["plain"]), "extends": len(g["extends"]),
                               "r1": _mean([at_k(r, variant, 1) for r in g["positive"]]),
                               "r3": _mean([at_k(r, variant, 3) for r in g["positive"]])}
        if t is not None:
            row |= {"recall": _mean([found(r, variant, t) for r in g["positive"]]),
                    "fire_plain": _mean([fires(r, variant, t) for r in g["plain"]]),
                    "fire_extends": _mean([fires(r, variant, t) for r in g["extends"]]),
                    "extends_names_baseline": _mean([names_baseline(r, variant, t) for r in g["extends"]]),
                    "hinted_per_write": _mean([len(hinted(r, variant, t)) for r in recs])}
        out[name] = row
    return out


def read_lines(holdout: Sequence[dict[str, Any]], choice: dict[str, Any]) -> list[dict[str, Any]]:
    g = groups(holdout)
    variant, t = choice["variant"], choice["t"]
    h1 = _ci([at_k(r, variant, 3) for r in g["positive"]])
    out = [{"id": "H1", "claim": f"Predecessor in the top 3 (`{variant}` query, no threshold)", "stat": h1,
            "line": LINES["H1"], "verdict": verdict(h1["mean"], h1["low"], LINES["H1"])}]
    if not choice["qualified"]:
        for ident in ("H2a", "H2b"):
            out.append({"id": ident, "claim": "no (variant, t) met the dev fire-rate cap", "stat": None,
                        "line": LINES[ident], "verdict": "miss (by rule)"})
        return out
    h2a = _ci([found(r, variant, t) for r in g["positive"]])
    h2b = _ci([fires(r, variant, t) for r in g["plain"]])
    line_b = LINES["H2b"]
    vb = "confirmed" if h2b["high"] <= line_b + _EPS else ("point pass" if h2b["mean"] <= line_b + _EPS else "miss")
    out += [{"id": "H2a", "claim": f"Predecessor hinted (`{variant}`, coverage >= {t:.2f})", "stat": h2a,
             "line": LINES["H2a"], "verdict": verdict(h2a["mean"], h2a["low"], LINES["H2a"])},
            {"id": "H2b", "claim": f"Plain writes with any hint (`{variant}`, coverage >= {t:.2f}); lower is better",
             "stat": h2b, "line": line_b, "verdict": vb}]
    return out


def _f(x: float | None) -> str:
    return "–" if x is None or x != x else f"{x:.3f}"


def render(split: str, records: Sequence[dict[str, Any]], choice: dict[str, Any],
           lines: list[dict[str, Any]] | None) -> str:
    o = [f"# Mode C: write-time supersession candidates ({split})", "",
         "Rules: [PLAN.md](../PLAN.md), \"Mode C\". Each probe is `search(card text, k=5)` just before the write; "
         "a hint names up to 3 top results whose `coverage` is at least the threshold. No LLM is involved.", ""]
    sel = f"`{choice['variant']}`, coverage >= {choice['t']:.2f}" if choice["qualified"] else \
        f"none qualified (H1 uses `{choice['variant']}`)"
    o += [f"Selection on `dev`: {sel}.", ""]
    if lines:
        o += ["| Line | Claim | Point | 95% interval | Line | Verdict |", "| --- | --- | --- | --- | --- | --- |"]
        for ln in lines:
            s = ln["stat"]
            point, ci = (_f(s["mean"]), f"[{_f(s['low'])}, {_f(s['high'])}]") if s else ("–", "")
            o.append(f"| {ln['id']} | {ln['claim']} | {point} | {ci} | {ln['line']:.2f} | **{ln['verdict']}** |")
        o.append("")
    o += ["| Set | Positives | Plain | Extends | R@1 | R@3 | Recall | Fire (plain) | Fire (extends) | "
          "Extends hint names its baseline | Hinted per write |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, r in describe(records, choice["variant"], choice["t"]).items():
        o.append(f"| {name} | {r['positives']} | {r['plain']} | {r['extends']} | {_f(r['r1'])} | {_f(r['r3'])} | "
                 f"{_f(r.get('recall'))} | {_f(r.get('fire_plain'))} | {_f(r.get('fire_extends'))} | "
                 f"{_f(r.get('extends_names_baseline'))} | {_f(r.get('hinted_per_write'))} |")
    o.append("")
    if split == "dev":
        o += ["## Grid (dev)", "", "| Variant | t | Recall | Fire (plain) | Fire (extends) |", "| --- | --- | --- | --- | --- |"]
        for r in grid(records):
            o.append(f"| {r['variant']} | {r['t']:.2f} | {_f(r['recall'])} | {_f(r['fire_plain'])} | {_f(r['fire_extends'])} |")
        o.append("")
    return "\n".join(o)


def save(results: Path, split: str, records: Sequence[dict[str, Any]], payload: dict[str, Any], report: str) -> None:
    results.mkdir(exist_ok=True)
    with open(results / f"hints_{split}.jsonl", "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (results / f"hints_{split}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (results / f"hints_{split}.md").write_text(report + "\n", encoding="utf-8")
