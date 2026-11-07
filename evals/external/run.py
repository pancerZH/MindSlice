"""Run MindSlice on external memory benchmarks, deterministically and offline (no LLM anywhere).

    python -m evals.external fetch                 # download the pinned files (about 330 MB) and verify them
    python -m evals.external check                 # digests, decoding, and judgment mapping; scores nothing
    python -m evals.external run                   # every dataset, printed
    python -m evals.external run --write           # also write results/
    python -m evals.external report                # re-summarize results/ from its saved records
    python -m evals.external run --datasets locomo,mab-sh --jobs 8

Data lives outside the repository (``$MINDSLICE_EVAL_DATA``, default ``~/.cache/mindslice/evals``).
Rules: PLAN.md. How to read the results: README.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import mindslice
from mindslice.lexical import analyzer_signature

from . import sources
from .checks import CHECKS
from .datasets import LOADERS, SOURCE_OF, Haystack
from .harness import K, built, run_in_tmp
from .score import (METRICS, auroc_ci, group_by, levels, mean_ci, paired_ci, state, verdict_of)

HERE = Path(__file__).parent
RESULTS = HERE / "results"
DATASETS = tuple(LOADERS)
LINEAGE_DATASETS = ("longmemeval-s", "meme-filler32k", "mab-sh")  # Mode B (PLAN.md)
STATE_GRANULARITY = {"longmemeval-s": "round", "meme-filler32k": "round", "mab-sh": "turn"}

# ---------------------------------------------------------------------------
# Pre-registered lines (PLAN.md, "Lines"). Fixed before any benchmark question was searched.
# ---------------------------------------------------------------------------
ABSTENTION_LINES = (
    {"id": "A1", "dataset": "longmemeval-s", "granularity": "round", "signal": "coverage_max", "line": 0.90,
     "claim": "LongMemEval-S: coverage separates abstention questions (AUROC)"},
    {"id": "A2", "dataset": "longmemeval-s", "granularity": "round", "signal": "matched_share", "line": 0.90,
     "claim": "LongMemEval-S: unmatched_terms separates abstention questions (AUROC)"},
    {"id": "A3", "dataset": "locomo", "granularity": "turn", "signal": "coverage_max", "line": 0.90,
     "claim": "LoCoMo: coverage separates adversarial questions (AUROC)"},
    {"id": "A4", "dataset": "locomo", "granularity": "turn", "signal": "matched_share", "line": 0.90,
     "claim": "LoCoMo: unmatched_terms separates adversarial questions (AUROC)"},
)
STRUCTURE_LINES = (
    ("B1", "root-forwarding", None, "read(old root value) forwards to the change card"),
    ("B2", "root-unrebased", None, "...and lists exactly its extensions as unrebased_extensions"),
    ("B3", "dependent-flagged", None, "read(dependent) names the root change in baseline_superseded_by (1- and 2-hop)"),
    ("B4", "rule-attached", None, "Cascade: the replacement rule is in the dependent's extensions"),
    ("B5", "deleted-unreadable", None, "Deleted cards raise not_found"),
    ("B6", "deleted-never-returned", None, "Deleted cards never appear in search results"),
    ("B7", "dependent-of-deleted-flagged", None, "A card extending a deleted card reports missing_baselines"),
    ("B8", "history-chain", None, "Tracking: the supersedes chain rebuilds the full history in order"),
    ("B9", "history-forwarding", None, "Tracking: read(first value) forwards to the latest along the chain"),
    ("B10", "stale-forwarding", None, "Knowledge updates and conflicts: read(stale) forwards to the current card"),
)
ABLATION_LINES = (
    {"id": "C1", "stat": "flat", "metric": "stale-first", "line": 0.20,
     "claim": "Without lineage, a stale fact outranks the current one often (pooled, flat)"},
    {"id": "C2", "stat": "flat-minus-lineage", "metric": "stale-first", "line": 0.20,
     "claim": "Lineage cuts stale-outranks-current by at least 0.20 (pooled, paired)"},
    {"id": "C3", "stat": "lineage-minus-flat", "metric": "current@10", "line": -0.02,
     "claim": "Lineage costs current-fact Recall@10 at most 0.02 (pooled, paired)"},
)


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def _job(args: tuple[Haystack, str, bool]) -> tuple[list[dict], list[dict]]:
    h, granularity, lineage = args
    check = CHECKS.get(h.dataset) if lineage else None
    records, _, rows = run_in_tmp(h, granularity, lineage, check)
    return records, rows or []


def jobs_for(h: Haystack) -> list[tuple[Haystack, str, bool]]:
    out = [(h, g, False) for g in h.granularities]
    if h.dataset in LINEAGE_DATASETS and h.lineage is not None and (h.lineage.supersedes or h.lineage.extends or h.lineage.deletes):
        out.append((h, STATE_GRANULARITY[h.dataset], True))
    return out


def run_all(datasets: tuple[str, ...], workers: int, root: Path | None, log=print) -> tuple[list[dict], list[dict], dict]:
    records: list[dict] = []
    checks: list[dict] = []
    info: dict[str, Any] = {}
    for name in datasets:
        t0 = time.time()
        haystacks = list(LOADERS[name](root))
        info[name] = _dataset_info(haystacks)
        work = [j for h in haystacks for j in jobs_for(h)]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for recs, rows in pool.map(_job, work, chunksize=1):
                records += recs
                checks += rows
        log(f"{name}: {len(haystacks)} haystacks, {len(work)} workspaces, {time.time() - t0:.0f}s")
    key = lambda r: (r["dataset"], r["haystack"], r["id"], r["granularity"], r["variant"])
    records.sort(key=key)
    checks.sort(key=lambda r: (r["dataset"], r["haystack"], r["check"], r["subject"]))
    return records, checks, info


def _dataset_info(haystacks: list[Haystack]) -> dict[str, Any]:
    out: dict[str, Any] = {"haystacks": len(haystacks), "questions": sum(len(h.questions) for h in haystacks),
                           "cards": {g: sum(len(built(h, g).cards) for h in haystacks) for g in haystacks[0].granularities}}
    extra: dict[str, int] = {}
    for h in haystacks:
        for k, v in h.info.items():
            if isinstance(v, int):
                extra[k] = extra.get(k, 0) + v
            elif k == "label_reasons":
                for kk, vv in v.items():
                    extra[kk] = extra.get(kk, 0) + vv
        if h.lineage is not None:
            for k, v in h.lineage.notes.items():
                extra[f"lineage: {k}"] = extra.get(f"lineage: {k}", 0) + v
    out["notes"] = extra
    out["unjudged"] = sum(1 for h in haystacks for q in h.questions if not q.gold and not q.gold_sessions)
    return out


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def _mode_a_group(r: dict) -> str:
    if r["dataset"].startswith("meme"):
        return f"{r['phase']}/{r['category']}"
    if r["dataset"] == "longmemeval-s" and not r["answerable"]:
        return "abstention"  # LongMemEval's own retrieval evaluation leaves these out; shown apart
    return r["category"]


def summarize_mode_a(records: list[dict]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    flat = [r for r in records if r["variant"] == "flat"]
    for (dataset, granularity), recs in sorted(group_by(flat, lambda r: (r["dataset"], r["granularity"])).items()):
        table: dict[str, Any] = {}
        for level in ("card", "session"):
            scored = [(r, levels(r).get(level)) for r in recs]
            scored = [(r, s) for r, s in scored if s is not None]
            if not scored:
                continue
            groups = group_by(scored, lambda rs: _mode_a_group(rs[0]))
            pooled = [rs for rs in scored if rs[0]["answerable"] and rs[0].get("phase", "after") == "after"]
            rows = {"all answerable" + (" (after)" if dataset.startswith("meme") else ""): pooled}
            rows.update(dict(sorted(groups.items())))
            table[level] = {name: {m: mean_ci([s[m] for _, s in rs]) for m in METRICS} for name, rs in rows.items() if rs}
        out[f"{dataset}/{granularity}"] = table
    return out


def summarize_abstention(records: list[dict]) -> dict[str, Any]:
    out = {}
    specs = [("longmemeval-s", "round", lambda r: r["answerable"]), ("longmemeval-s", "session", lambda r: r["answerable"]),
             ("locomo", "turn", lambda r: r["answerable"]), ("locomo", "session", lambda r: r["answerable"]),
             ("meme-filler32k", "round", lambda r: r.get("task") not in ("Abs", "Del"))]
    for dataset, gran, answerable in specs:
        recs = [r for r in records if r["dataset"] == dataset and r["granularity"] == gran and r["variant"] == "flat"
                and r.get("phase", "after") == "after"]
        if not recs:
            continue
        pos = [r for r in recs if answerable(r)]
        neg = [r for r in recs if not answerable(r)]
        entry = {"answerable": len(pos), "unanswerable": len(neg)}
        for signal, fn in (("coverage_max", lambda r: r["coverage_max"]), ("matched_share", lambda r: 1 - r["unmatched_share"])):
            entry[signal] = auroc_ci([fn(r) for r in pos], [fn(r) for r in neg])
        entry["any_unmatched"] = {"answerable": _share(pos, lambda r: bool(r["unmatched_terms"])),
                                  "unanswerable": _share(neg, lambda r: bool(r["unmatched_terms"]))}
        entry["mean_coverage_max"] = {"answerable": _mean(pos, "coverage_max"), "unanswerable": _mean(neg, "coverage_max")}
        out[f"{dataset}/{gran}"] = entry
    return out


def _share(recs, pred) -> float:
    return round(sum(1 for r in recs if pred(r)) / len(recs), 4) if recs else float("nan")


def _mean(recs, key) -> float:
    return round(sum(r[key] for r in recs) / len(recs), 4) if recs else float("nan")


def _state_group(r: dict) -> str | None:
    if r["dataset"] == "meme-filler32k":
        if r.get("phase") != "after" or r.get("task") not in ("Cas", "Abs", "Del", "Tr"):
            return None
        return f"meme/{r['category']}"
    if r["dataset"] == "longmemeval-s" and r.get("stale") and r.get("current"):
        return "longmemeval-s/knowledge-update"
    if r["dataset"] == "mab-sh" and r.get("stale") and r.get("current"):
        return "mab-sh/conflict"
    return None


def summarize_ablation(records: list[dict]) -> dict[str, Any]:
    pairs: dict[str, list[tuple[dict, dict]]] = {}
    # Keyed by dataset too: MEME's filler32k and nofiller variants share question ids.
    index = {(r["dataset"], r["id"], r["granularity"], r["variant"]): r for r in records}
    for r in records:
        if r["variant"] != "lineage":
            continue
        g = _state_group(r)
        flat = index.get((r["dataset"], r["id"], r["granularity"], "flat"))
        if g and flat is not None:
            pairs.setdefault(g, []).append((flat, r))
    out: dict[str, Any] = {"groups": {}, "pooled": {}}
    for g, ps in sorted(pairs.items()):
        f_scores = [state(f) for f, _ in ps]
        l_scores = [state(l) for _, l in ps]
        metrics = sorted(set().union(*f_scores) & set().union(*l_scores))
        entry = {}
        for m in metrics:
            idx = [i for i, (a, b) in enumerate(zip(f_scores, l_scores)) if m in a and m in b]
            fv, lv = [f_scores[i][m] for i in idx], [l_scores[i][m] for i in idx]
            entry[m] = {"flat": mean_ci(fv), "lineage": mean_ci(lv), "lineage-minus-flat": paired_ci(lv, fv)}
        out["groups"][g] = {"questions": len(ps), "metrics": entry}
    pooled = [p for g, ps in pairs.items() if g in ("meme/Cas-hop1", "meme/Cas-hop2", "longmemeval-s/knowledge-update",
                                                    "mab-sh/conflict") for p in ps]
    for m in ("stale-first", "current@10", "stale@10"):
        fv = [state(f)[m] for f, l in pooled if m in state(f)]
        lv = [state(l)[m] for f, l in pooled if m in state(l)]
        out["pooled"][m] = {"flat": mean_ci(fv), "lineage": mean_ci(lv), "lineage-minus-flat": paired_ci(lv, fv),
                            "flat-minus-lineage": paired_ci(fv, lv)}
    out["pooled"]["questions"] = len(pooled)
    return out


def summarize_checks(checks: list[dict]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for (check, group), rows in sorted(group_by(checks, lambda r: (r["check"], r.get("group", ""))).items()):
        if check == "e2e":
            continue
        entry = {"ok": sum(r["ok"] for r in rows), "total": len(rows),
                 "failures": [r["subject"] for r in rows if not r["ok"]][:5]}
        signals = {r["signal"] for r in rows if r.get("signal")}
        if len(signals) > 1:
            entry["signals"] = {sig: sum(1 for r in rows if r.get("signal") == sig) for sig in sorted(signals)}
        out.setdefault(check, {})[group or "all"] = entry
    e2e = {}
    for group, rows in sorted(group_by([r for r in checks if r["check"] == "e2e"], lambda r: r["group"]).items()):
        n = len(rows)
        e2e[group] = {"questions": n, **{k: round(sum(bool(r[k]) for r in rows) / n, 4)
                                         for k in ("found", "preview_flag", "read_flag", "rule_reachable", "ok")}}
    out["e2e"] = e2e
    return out


DISTINCTIVE = 0.10  # a query word in fewer than 10% of the haystack's cards (exploratory, chosen after run 1)


def gap_analysis(records: list[dict]) -> dict[str, Any]:
    """First-page misses at card level (exploratory): does the judged card share the question's distinctive words?

    * ``vocabulary gap``: the question has distinctive words, and no judged card contains any of them.
    * ``outranked``: a judged card contains one, but ten other cards rank higher.
    * ``no distinctive word``: every query word is in at least 10% of the cards.
    """
    out = {}
    flat = [r for r in records if r["variant"] == "flat" and r["granularity"] != "session" and r["answerable"]
            and r["gold"] and r.get("phase", "after") == "after"]
    for (dataset, gran), recs in sorted(group_by(flat, lambda r: (r["dataset"], r["granularity"])).items()):
        misses = [r for r in recs if "gold_rank" in r]
        kinds: dict[str, list[dict]] = {"vocabulary gap": [], "outranked": [], "no distinctive word": []}
        for r in misses:
            words = r.get("miss_words", [])
            distinctive = [w for w in words if w["df"] < DISTINCTIVE]
            if not distinctive:
                kinds["no distinctive word"].append(r)
            elif not any(w["in_gold"] for w in distinctive):
                kinds["vocabulary gap"].append(r)
            else:
                kinds["outranked"].append(r)
        ranks = sorted(r["gold_rank"] for r in kinds["outranked"] if r["gold_rank"] is not None)
        out[f"{dataset}/{gran}"] = {
            "questions": len(recs), "first-page misses": len(misses), **{k: len(v) for k, v in kinds.items()},
            "median rank (outranked)": ranks[len(ranks) // 2] if ranks else None,
            "examples (vocabulary gap)": [
                {"id": r["id"], "query": r["query"],
                 "missing": [w["word"] for w in r["miss_words"] if w["df"] < DISTINCTIVE and not w["in_gold"]]}
                for r in kinds["vocabulary gap"][:6]],
        }
    return out


def read_lines(summary: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for spec in ABSTENTION_LINES:
        entry = summary["abstention"].get(f"{spec['dataset']}/{spec['granularity']}")
        if entry:
            stat = entry[spec["signal"]]
            out.append({**spec, "point": stat["mean"], "low": stat["low"], "high": stat["high"],
                        "verdict": verdict_of(stat, spec["line"])})
    checks = summary["checks"]
    for ident, check, group, claim in STRUCTURE_LINES:
        groups = checks.get(check)
        if not groups:
            continue
        ok, total = sum(g["ok"] for g in groups.values()), sum(g["total"] for g in groups.values())
        out.append({"id": ident, "claim": claim, "ok": ok, "total": total,
                    "verdict": "pass" if ok == total and total else f"fail ({total - ok} of {total})"})
    hop2 = [g for name, g in checks.get("e2e", {}).items() if name.endswith("hop2")]
    if hop2:
        flagged = sum(g["preview_flag"] * g["questions"] for g in hop2)
        found = sum(g["found"] * g["questions"] for g in hop2)
        out.append({"id": "B11", "claim": "Known gap: search previews flag 2-hop dependents (expected: they don't)",
                    "ok": round(flagged), "total": round(found),
                    "verdict": "gap confirmed" if flagged == 0 else f"previews flag {round(flagged)} of {round(found)}"})
    pooled = summary["ablation"]["pooled"]
    for spec in ABLATION_LINES:
        stat = pooled[spec["metric"]][spec["stat"]]
        out.append({**spec, "point": stat["mean"], "low": stat["low"], "high": stat["high"],
                    "verdict": verdict_of(stat, spec["line"])})
    return out


def summarize(records: list[dict], checks: list[dict]) -> dict[str, Any]:
    summary = {"mode_a": summarize_mode_a(records), "abstention": summarize_abstention(records),
               "ablation": summarize_ablation(records), "checks": summarize_checks(checks), "gaps": gap_analysis(records)}
    summary["lines"] = read_lines(summary)
    return summary


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _ci(stat: dict[str, float]) -> str:
    if not stat or stat.get("n", 1) == 0 or math.isnan(stat["mean"]):
        return "–"
    return f"{stat['mean']:.3f} [{stat['low']:.3f}, {stat['high']:.3f}]"


def _f(stat: dict[str, float]) -> str:
    return "–" if not stat or math.isnan(stat["mean"]) else f"{stat['mean']:.3f}"


TITLES = {"longmemeval-s": "LongMemEval-S (cleaned)", "locomo": "LoCoMo", "meme-filler32k": "MEME (filler32k)",
          "meme-nofiller": "MEME (nofiller)", "mab-sh": "MemoryAgentBench FactConsolidation-SH (derived labels)"}


def render(summary: dict[str, Any], info: dict[str, Any]) -> str:
    o = ["# External benchmark results", "",
         "Generated by `python -m evals.external run --write`. Rules: [PLAN.md](../PLAN.md); findings: "
         "[REPORT.md](../REPORT.md). Brackets are 95% bootstrap intervals over questions; differences are paired. "
         f"Every search is `search(question, k={K})` with defaults; no LLM is involved.", ""]
    o += ["## Verdicts", "", "| Line | Claim | Point | 95% interval | Line | Verdict |", "| --- | --- | --- | --- | --- | --- |"]
    for l in summary["lines"]:
        if "point" in l:
            o.append(f"| {l['id']} | {l['claim']} | {l['point']:.3f} | [{l['low']:.3f}, {l['high']:.3f}] | {l['line']:.2f} | **{l['verdict']}** |")
        else:
            o.append(f"| {l['id']} | {l['claim']} | {l['ok']} / {l['total']} | | all | **{l['verdict']}** |")
    o.append("")

    o += ["## Mode A: retrieval on flat cards", "",
          "`card` scores the ranked cards against the cards holding an evidence turn; `session` scores the ranked "
          "cards' sessions (first occurrence) against the evidence sessions. Pooled rows exclude unanswerable "
          "questions (LongMemEval abstention, LoCoMo adversarial) and MEME's before-change questions.", ""]
    for key, table in summary["mode_a"].items():
        dataset, gran = key.split("/")
        for level, rows in table.items():
            o += [f"### {TITLES[dataset]}: {gran} cards, {level} level", "",
                  "| Group | n | Recall@5 | Recall@10 | MRR@10 | nDCG@5 | All@10 |", "| --- | --- | --- | --- | --- | --- | --- |"]
            for name, ms in rows.items():
                n = ms["recall@10"]["n"]
                cells = [_ci(ms[m]) if name.startswith("all") else _f(ms[m]) for m in METRICS]
                o.append(f"| {name} | {n} | " + " | ".join(cells) + " |")
            o.append("")

    o += ["## Abstention: do `coverage` and `unmatched_terms` separate unanswerable questions?", "",
          "AUROC = probability that a random answerable question scores higher than a random unanswerable one "
          "(0.5 = no separation). `coverage_max` is the best `coverage` on the first page; `matched share` is "
          "1 − (unmatched query words / query words). MEME's Absence and Deletion questions are answerable "
          "lexically by design; that row shows what lexical signals can't see.", "",
          "| Corpus | Answerable | Unanswerable | AUROC coverage_max | AUROC matched share | Any unmatched (ans / unans) | Mean coverage_max (ans / unans) |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for key, e in summary["abstention"].items():
        o.append(f"| {key} | {e['answerable']} | {e['unanswerable']} | {_ci(e['coverage_max'])} | {_ci(e['matched_share'])} | "
                 f"{e['any_unmatched']['answerable']:.3f} / {e['any_unmatched']['unanswerable']:.3f} | "
                 f"{e['mean_coverage_max']['answerable']:.3f} / {e['mean_coverage_max']['unanswerable']:.3f} |")
    o.append("")

    o += ["## Mode B: lineage structure (read() and search() against the compiled lineage)", "",
          "| Check | Group | OK | Total | First failures |", "| --- | --- | --- | --- | --- |"]
    for check, groups in summary["checks"].items():
        if check == "e2e":
            continue
        for g, v in groups.items():
            note = ", ".join(f"{k}: {n}" for k, n in v.get("signals", {}).items())
            o.append(f"| {check} | {g} | {v['ok']} | {v['total']} | {', '.join(v['failures']) or note} |")
    o += ["", "`no-rule` is not a line: its failures are Absence questions whose target is also the middle of a "
          "2-hop chain, so MEME declares its replacement rule while labeling the question \"Uncertain\" (REPORT.md).",
          "", "### End to end: from the question's first search page (MEME, lineage)", "",
          "| Group | Questions | Dependent or rule on page | Flagged in preview | Flagged after read | Rule reachable | All signals |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for g, v in summary["checks"].get("e2e", {}).items():
        rule = f"{v['rule_reachable']:.3f}" if g.startswith("Cas") else "n/a"
        o.append(f"| {g} | {v['questions']} | {v['found']:.3f} | {v['preview_flag']:.3f} | {v['read_flag']:.3f} | {rule} | {v['ok']:.3f} |")
    o.append("")

    o += ["## Mode B: lineage versus flat cards (same cards, same questions)", "",
          "`stale@10`: an outdated fact is on the first page unwarned. `stale-first`: it ranks above every current "
          "card. `current@10`: share of current-value cards on the page. `value-leak@10` (Deletion): some card other "
          "than the deletion request still states the deleted value. `history@10` (Tracking): share of the value "
          "history among results; `history-named@10` also counts `matched_via_superseded` entries.", "",
          "| Group | n | Metric | Flat | Lineage | Lineage − flat |", "| --- | --- | --- | --- | --- | --- |"]
    for g, v in summary["ablation"]["groups"].items():
        for m, s in v["metrics"].items():
            o.append(f"| {g} | {v['questions']} | {m} | {_ci(s['flat'])} | {_ci(s['lineage'])} | {_ci(s['lineage-minus-flat'])} |")
    p = summary["ablation"]["pooled"]
    o += ["", f"Pooled (MEME Cascade, LongMemEval knowledge updates, MemoryAgentBench conflicts; {p['questions']} questions):", "",
          "| Metric | Flat | Lineage | Lineage − flat |", "| --- | --- | --- | --- |"]
    for m in ("stale-first", "stale@10", "current@10"):
        o.append(f"| {m} | {_ci(p[m]['flat'])} | {_ci(p[m]['lineage'])} | {_ci(p[m]['lineage-minus-flat'])} |")
    o.append("")

    o += ["## Where lexical search misses (flat, card level, answerable; exploratory)", "",
          f"A query word is *distinctive* when fewer than {DISTINCTIVE:.0%} of the haystack's cards contain it. "
          "`vocabulary gap`: no judged card contains any of the question's distinctive words. `outranked`: one does, "
          "but ten other cards rank higher. This reading was defined after run 1 (PLAN.md ledger).", "",
          "| Corpus | Questions | First-page misses | Vocabulary gap | Outranked | No distinctive word | Median rank (outranked) |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for key, g in summary["gaps"].items():
        o.append(f"| {key} | {g['questions']} | {g['first-page misses']} | {g['vocabulary gap']} | {g['outranked']} | "
                 f"{g['no distinctive word']} | {g['median rank (outranked)'] or '–'} |")
    o += ["", "Examples of vocabulary gaps (the distinctive words no judged card contains):", ""]
    for key, g in summary["gaps"].items():
        for ex in g["examples (vocabulary gap)"][:3]:
            o.append(f"- `{key}` {ex['id']}: \"{ex['query']}\" (missing: {', '.join(ex['missing'])})")
    o.append("")
    o += ["## Data", "", "| Dataset | Haystacks | Questions | Cards | Unjudged | Notes |", "| --- | --- | --- | --- | --- | --- |"]
    for name, d in info.items():
        cards = ", ".join(f"{k} {v}" for k, v in d["cards"].items())
        notes = "; ".join(f"{k}: {v}" for k, v in d["notes"].items())
        o.append(f"| {TITLES[name]} | {d['haystacks']} | {d['questions']} | {cards} | {d['unjudged']} | {notes} |")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------
# Environment, check, CLI
# ---------------------------------------------------------------------------


def harness_digest() -> str:
    files = sorted(p for p in HERE.glob("*.py"))
    return hashlib.sha256(b"".join(f.name.encode() + b"\0" + f.read_bytes() for f in files)).hexdigest()


def environment() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=HERE).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    package = Path(mindslice.__file__).parent
    engine = hashlib.sha256(b"".join(f.name.encode() + b"\0" + f.read_bytes() for f in sorted(package.glob("*.py"))))
    return {"mindslice": mindslice.__version__, "commit": git("rev-parse", "--short", "HEAD"),
            "engine_dirty": bool(git("status", "--porcelain", "--", str(package))), "engine_digest": engine.hexdigest(),
            "harness_digest": harness_digest(), "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
            "unicode": unicodedata.unidata_version, "analyzer": analyzer_signature(), "k": K,
            "sources": {k: {"url": s.url, "sha256": s.sha256} for k, s in sources.SOURCES.items()}}


def check(root: Path | None, datasets: tuple[str, ...]) -> list[str]:
    issues = sources.problems(root, tuple(dict.fromkeys(SOURCE_OF[d] for d in datasets)))
    if issues:
        return issues
    for name in datasets:
        for h in LOADERS[name](root):
            for g in h.granularities:
                b = built(h, g)
                for q in h.questions:
                    missing = [u for u in q.gold if u not in b.card_of_unit]
                    if missing:
                        issues.append(f"{q.id}: {len(missing)} evidence turns hold no {g} card")
                paths = [c.path for c in b.cards]
                if len(paths) != len(set(paths)):
                    issues.append(f"{h.key}: duplicate {g} card paths")
    return issues


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.external", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", help=f"data directory (default ${sources.DATA_ENV} or ~/.cache/mindslice/evals)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch", help="download and verify the pinned dataset files")
    c = sub.add_parser("check", help="digests, decoding and judgment mapping (scores nothing)")
    c.add_argument("--datasets", default=",".join(DATASETS))
    r = sub.add_parser("run", help="run every dataset")
    r.add_argument("--datasets", default=",".join(DATASETS))
    r.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    r.add_argument("--write", action="store_true", help="write results/ (records first, then the summary)")
    sub.add_parser("report", help="re-summarize results/ from its saved records (searches nothing)")
    args = p.parse_args(argv)
    root = sources.data_dir(args.data)

    if args.command == "fetch":
        failures = sources.fetch(root)
        print("\n".join(failures) or "all files present and verified")
        return 1 if failures else 0
    if args.command == "report":
        records = _read_jsonl(RESULTS / "per_query.jsonl")
        checks = _read_jsonl(RESULTS / "checks.jsonl")
        run = json.loads((RESULTS / "run.json").read_text(encoding="utf-8"))
        _write_summary(run, records, checks)
        return 0
    datasets = tuple(d for d in args.datasets.split(",") if d)
    unknown = [d for d in datasets if d not in LOADERS]
    if unknown:
        print(f"unknown dataset(s): {', '.join(unknown)} (have: {', '.join(DATASETS)})")
        return 2
    issues = check(root, datasets)
    if args.command == "check" or issues:
        print("\n".join(issues) or "data OK")
        return 1 if issues else 0

    records, checks, info = run_all(datasets, args.jobs, root, log=lambda s: print(s, file=sys.stderr))
    run = {"environment": environment(), "datasets": list(datasets), "data": info}
    if not args.write:
        print(render(summarize(records, checks), info))
        return 0
    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "per_query.jsonl", "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(RESULTS / "checks.jsonl", "w", encoding="utf-8") as fh:
        for row in checks:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    (RESULTS / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _write_summary(run, records, checks)
    return 0


def _read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _write_summary(run: dict, records: list[dict], checks: list[dict]) -> None:
    summary = summarize(records, checks)
    report = render(summary, run["data"])
    (RESULTS / "summary.md").write_text(report, encoding="utf-8")
    run = {**run, "summary": summary, "summarized_by": harness_digest()}  # may differ after `report`
    (RESULTS / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    sys.exit(main())
