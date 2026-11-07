"""Run the retrieval evaluation.

    python -m evals.retrieval check                      # integrity + digests (no system is scored)
    python -m evals.retrieval freeze                     # record data digests in data/DIGESTS.json
    python -m evals.retrieval run                        # dev and limits splits, printed
    python -m evals.retrieval run --splits dev,holdout,limits,holdout-2,holdout-3 --write   # also write results/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

import mindslice
from mindslice.lexical import analyzer_signature

from .dataset import (
    ALIASED,
    CORPORA,
    DIGESTS_FILE,
    SPLITS,
    Query,
    aliased_problems,
    build_workspace,
    digests,
    frozen_digests,
    load_queries,
    problems,
)
from .metrics import BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED, METRICS, interval, resamples, score, verdict
from .systems import BASELINE, SYSTEMS, data_for, ranked, system

RESULTS = Path(__file__).parent / "results"
K = 10  # search()'s default page: what an agent sees first

# Pre-registered in PLAN.md before the split they read was scored. L1-L6 read `holdout`, L9-L12 `holdout-2`.
# L7, L8 and L13-L17 (coverage-first versus BM25 order) were decided on the archived engine and retired; their
# record is in results/archive/2026-11-06-coverage-first-engine/.
LINES = (
    {"id": "L1", "group": "holdout/en", "metric": "ndcg@5", "line": 0.80, "claim": "English nDCG@5 at least 0.80"},
    {"id": "L2", "group": "holdout/zh", "metric": "ndcg@5", "line": 0.80, "claim": "Chinese nDCG@5 at least 0.80"},
    {"id": "L3", "group": "holdout/en", "metric": "recall@10", "line": 0.90, "claim": "English Recall@10 at least 0.90"},
    {"id": "L4", "group": "holdout/zh", "metric": "recall@10", "line": 0.90, "claim": "Chinese Recall@10 at least 0.90"},
    {"id": "L5", "group": "holdout/zh", "metric": "ndcg@5", "versus": "v1-baseline", "line": 0.30,
     "claim": "Script-aware analysis adds at least 0.30 Chinese nDCG@5 over v1"},
    {"id": "L6", "group": "holdout/zh", "metric": "ndcg@5", "versus": "strict-phrase", "line": 0.0,
     "claim": "OR-ed bigrams are no worse than strict phrases (Chinese)"},
    {"id": "L9", "group": "holdout-2/en", "metric": "ndcg@5", "line": 0.70, "claim": "Harder English nDCG@5 at least 0.70"},
    {"id": "L10", "group": "holdout-2/zh", "metric": "ndcg@5", "line": 0.70, "claim": "Harder Chinese nDCG@5 at least 0.70"},
    {"id": "L11", "group": "holdout-2/en/tiny", "metric": "ndcg@5", "line": 0.70, "claim": "Tiny English nDCG@5 at least 0.70"},
    {"id": "L12", "group": "holdout-2/zh/tiny", "metric": "ndcg@5", "line": 0.70, "claim": "Tiny Chinese nDCG@5 at least 0.70"},
    # holdout-3 (queries written blind to the engine). A "gain" line reads that system minus mindslice.
    {"id": "L18", "group": "holdout-3/en/natural", "metric": "ndcg@5", "line": 0.80,
     "claim": "Blind English natural queries: nDCG@5 at least 0.80"},
    {"id": "L19", "group": "holdout-3/zh/natural", "metric": "ndcg@5", "line": 0.80,
     "claim": "Blind Chinese natural queries: nDCG@5 at least 0.80"},
    {"id": "L20", "group": "holdout-3/all/vocab-gap", "metric": "ndcg@5", "gain": "aliases", "line": 0.05,
     "claim": "Aliases add at least 0.05 on vocabulary-gap queries"},
    {"id": "L21", "group": "holdout-3/all/natural", "metric": "ndcg@5", "gain": "aliases", "line": -0.02,
     "claim": "Aliases cost natural queries at most 0.02"},
    {"id": "L22", "group": "holdout-3/all", "metric": "ndcg@5", "gain": "aliases", "line": 0.0,
     "claim": "Aliases are no worse overall (decision line)"},
    {"id": "L23", "group": "holdout-3/all/typo", "metric": "ndcg@5", "gain": "suggest-retry", "line": 0.0,
     "claim": "Retrying with did_you_mean is no worse on typos"},
    {"id": "L24", "group": "holdout-3/all", "metric": "ndcg@5", "gain": "suggest-retry", "line": 0.0,
     "claim": "Retrying with did_you_mean is no worse overall (decision line)"},
)
POOLED_SPLITS = ("holdout-2", "holdout-3")  # also summarized over all their queries, as "<split>/all"
# Category groups, per language ("<split>/<lang>/<name>") and pooled ("<split>/all/<name>").
CATEGORY_GROUPS = {
    "holdout-3": {"natural": ("natural",), "vocab-gap": ("own-words", "cross-lingual"), "typo": ("typo",)},
}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def group_of(q: Query) -> str:
    return f"{q.split}/{q.lang}" + ("" if q.corpus == "full" else "/tiny")


def rank_all(queries: list[Query], systems: tuple[str, ...] = SYSTEMS) -> list[dict[str, Any]]:
    records = []
    corpora = list(dict.fromkeys(q.corpus for q in queries))
    with tempfile.TemporaryDirectory(prefix="mindslice-eval-") as tmp:
        for name in systems:
            with system(name):
                for corpus in corpora:
                    ws = build_workspace(Path(tmp) / name / corpus / "ws", corpus, data_for(name))
                    try:
                        for q in (q for q in queries if q.corpus == corpus):
                            got = ranked(name, ws, q.text, K)
                            records.append({"system": name, "id": q.id, "split": q.split, "lang": q.lang,
                                            "corpus": q.corpus, "group": group_of(q), "category": q.category,
                                            "query": q.text, "ranked": got,
                                            **{m: round(v, 6) for m, v in score(got, q.relevant).items()}})
                    finally:
                        ws.close()
    order = {q.id: i for i, q in enumerate(queries)}
    records.sort(key=lambda r: (systems.index(r["system"]), order[r["id"]]))
    return records


def summarize(records: list[dict[str, Any]], systems: tuple[str, ...]) -> dict[str, Any]:
    """Per group (``split/lang`` or ``split/lang/tiny``, plus pooled ``split/all``): means with paired intervals."""
    by_key = {(r["system"], r["id"]): r for r in records}
    members: dict[str, list[str]] = {}
    for r in records:
        if r["system"] == systems[0]:
            members.setdefault(r["group"], []).append(r["id"])
            if r["split"] in POOLED_SPLITS:
                members.setdefault(f"{r['split']}/all", []).append(r["id"])
            for name, categories in CATEGORY_GROUPS.get(r["split"], {}).items():
                if r["category"] in categories:
                    members.setdefault(f"{r['split']}/{r['lang']}/{name}", []).append(r["id"])
                    members.setdefault(f"{r['split']}/all/{name}", []).append(r["id"])
    order = sorted(members, key=lambda g: (SPLITS.index(g.split("/")[0]), g.split("/")[1] == "all", g))
    groups: dict[str, Any] = {}
    for key in order:
        ids = sorted(members[key])
        draws = resamples(len(ids))  # one shared set of resamples per group: paired comparisons
        group: dict[str, Any] = {"queries": len(ids), "systems": {}}
        for name in systems:
            entry: dict[str, Any] = {}
            for m in METRICS:
                mean, low, high = interval([by_key[name, i][m] for i in ids], draws)
                entry[m] = {"mean": round(mean, 4), "low": round(low, 4), "high": round(high, 4)}
                if name != BASELINE:
                    d, dlow, dhigh = interval([by_key[BASELINE, i][m] - by_key[name, i][m] for i in ids], draws)
                    entry[f"{m} baseline minus this"] = {"mean": round(d, 4), "low": round(dlow, 4), "high": round(dhigh, 4)}
            group["systems"][name] = entry
        groups[key] = group
    return groups


def read_lines(summary: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for spec in LINES:
        group = summary.get(spec["group"])
        if group is None:
            continue
        if "versus" in spec:
            stat = group["systems"][spec["versus"]][f"{spec['metric']} baseline minus this"]
        elif "gain" in spec:  # that system minus mindslice: the negated paired difference
            d = group["systems"][spec["gain"]][f"{spec['metric']} baseline minus this"]
            stat = {"mean": 0.0 - d["mean"], "low": 0.0 - d["high"], "high": 0.0 - d["low"]}
        else:
            stat = group["systems"][BASELINE][spec["metric"]]
        out.append({**spec, "point": stat["mean"], "low": stat["low"], "high": stat["high"],
                    "verdict": verdict(stat["mean"], stat["low"], spec["line"])})
    return out


# Secondary reading of holdout-3 (PLAN.md, amendment before scoring): the same rankings, scored without the
# judgments on the other team's handbook. It shows verdicts against the same lines but decides nothing.
SECONDARY_SPLITS = ("holdout-3",)


def same_team(q: Query) -> dict[str, int]:
    other = "@kb-zh/" if q.lang == "en" else "@kb-en/"
    return {a: g for a, g in q.relevant.items() if not a.startswith(other)}


def secondary(records: list[dict[str, Any]], queries: list[Query],
              systems: tuple[str, ...]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    qmap = {q.id: q for q in queries}
    rescored = [{**r, **{m: round(v, 6) for m, v in score(r["ranked"], same_team(qmap[r["id"]])).items()}}
                for r in records if r["split"] in SECONDARY_SPLITS]
    if not rescored:
        return {}, []
    summary = summarize(rescored, systems)
    return summary, read_lines(summary)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def environment() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True, check=True,
                                  cwd=Path(__file__).parent).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    package = Path(mindslice.__file__).parent
    status = git("status", "--porcelain", "--", str(package))
    engine = hashlib.sha256(b"".join(f.name.encode() + b"\0" + f.read_bytes() for f in sorted(package.glob("*.py"))))
    return {"mindslice": mindslice.__version__, "engine_commit": git("rev-parse", "--short", "HEAD"),
            "engine_dirty": bool(status) if status is not None else None, "engine_digest": engine.hexdigest(),
            "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version, "unicode": unicodedata.unidata_version, "analyzer": analyzer_signature(),
            "k": K, "bootstrap": {"replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED}}


def _ci(stat: dict[str, float]) -> str:
    return f"{stat['mean']:.3f} [{stat['low']:.3f}, {stat['high']:.3f}]"


def render(records: list[dict[str, Any]], summary: dict[str, Any], lines: list[dict[str, Any]],
           queries: list[Query], systems: tuple[str, ...],
           second: tuple[dict[str, Any], list[dict[str, Any]]] = ({}, [])) -> str:
    out = ["# Retrieval evaluation results", "",
           "Generated by `python -m evals.retrieval run --write`. Rules: [PLAN.md](../PLAN.md). "
           "Brackets are 95% bootstrap intervals over queries; differences are paired.", ""]
    if lines:
        out += ["## Verdicts", "",
                "L1-L6 read `holdout` and L9-L12 `holdout-2`, re-read on the current engine (no longer fresh evidence). "
                "L18-L24 read `holdout-3`; for L20-L24 the point is that system minus `mindslice`.", "",
                "| Line | Claim | Point | 95% interval | Line | Verdict |", "| --- | --- | --- | --- | --- | --- |"]
        out += [f"| {l['id']} | {l['claim']} | {l['point']:.3f} | [{l['low']:.3f}, {l['high']:.3f}] | {l['line']:.2f} | "
                f"**{l['verdict']}** |" for l in lines]
        out.append("")
    second_summary, second_lines = second
    if second_lines:
        out += ["## Secondary reading: `holdout-3` with same-team judgments (decides nothing)", "",
                "The same rankings, scored without the grade-1 judgments on the other team's handbook "
                "(PLAN.md, amendment before scoring).", "",
                "| Line | Claim | Point | 95% interval | Line | Would be |", "| --- | --- | --- | --- | --- | --- |"]
        out += [f"| {l['id']} | {l['claim']} | {l['point']:.3f} | [{l['low']:.3f}, {l['high']:.3f}] | {l['line']:.2f} | "
                f"{l['verdict']} |" for l in second_lines]
        out += ["", "| Group | Queries | " + " | ".join(systems) + " |", "| --- | --- | " + " | ".join("---" for _ in systems) + " |"]
        for key, group in second_summary.items():
            cells = [f"{group['systems'][s]['ndcg@5']['mean']:.3f}" for s in systems]
            out.append(f"| {key} | {group['queries']} | " + " | ".join(cells) + " |")
        out.append("")
    for key, group in summary.items():
        split, lang, *rest = key.split("/")
        title = {"en": "English", "zh": "Chinese", "all": "all queries pooled"}[lang]
        if rest:
            title += ", tiny corpus" if rest == ["tiny"] else f", `{rest[0]}` queries"
        out += [f"## {split}: {title} ({group['queries']} queries)", "",
                "| System | nDCG@5 | Recall@10 | MRR@10 | mindslice minus system, nDCG@5 |", "| --- | --- | --- | --- | --- |"]
        for name in systems:
            e = group["systems"][name]
            diff = _ci(e["ndcg@5 baseline minus this"]) if name != BASELINE else ""
            out.append(f"| {name} | {_ci(e['ndcg@5'])} | {_ci(e['recall@10'])} | {_ci(e['mrr@10'])} | {diff} |")
        out.append("")
    out += ["## nDCG@5 by category", "", "| Group | Category | Queries | " + " | ".join(systems) + " |",
            "| --- | --- | --- | " + " | ".join("---" for _ in systems) + " |"]
    cats = sorted({(r["group"], r["category"]) for r in records}, key=lambda c: (SPLITS.index(c[0].split("/")[0]), c))
    for grp, cat in cats:
        rows = [r for r in records if (r["group"], r["category"]) == (grp, cat)]
        n = len({r["id"] for r in rows})
        cells = [f"{sum(r['ndcg@5'] for r in rows if r['system'] == s) / n:.3f}" for s in systems]
        out.append(f"| {grp} | {cat} | {n} | " + " | ".join(cells) + " |")
    out.append("")
    qmap = {q.id: q for q in queries}
    misses = [r for r in records if r["system"] == BASELINE and r["ndcg@5"] < 0.5]
    out += ["## Queries where mindslice scores nDCG@5 below 0.5", ""]
    if misses:
        out += ["| Query | Group | Text | Answer (grade 2) | mindslice top 3 | nDCG@5 |", "| --- | --- | --- | --- | --- | --- |"]
        for r in misses:
            answer = ", ".join(a for a, g in qmap[r["id"]].relevant.items() if g == 2)
            top = ", ".join(r["ranked"][:3]) or "(nothing)"
            out.append(f"| {r['id']} | {r['group']} | {r['query']} | {answer} | {top} | {r['ndcg@5']:.3f} |")
    else:
        out.append("None.")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def check() -> list[str]:
    queries = load_queries()
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="mindslice-eval-check-") as tmp:
        for corpus in CORPORA:
            ws = build_workspace(Path(tmp) / corpus / "ws", corpus)
            try:
                issues += problems([q for q in queries if q.corpus == corpus], ws)
            finally:
                ws.close()
        unknown = sorted({q.corpus for q in queries} - set(CORPORA))
        issues += [f"unknown corpus {c!r}" for c in unknown]
        aliased = aliased_problems()
        issues += aliased
        if ALIASED.exists() and not aliased:
            for corpus in CORPORA:  # aliases must not break validation (duplicates, collisions with paths)
                ws = build_workspace(Path(tmp) / "aliased" / corpus / "ws", corpus, ALIASED)
                try:
                    report = ws.validate()
                    issues += [f"aliased {corpus}: {i['code']}: {i['message']}" for i in report["errors"] + report["warnings"]]
                finally:
                    ws.close()
    if DIGESTS_FILE.exists():
        frozen, now = frozen_digests(), digests(queries)
        issues += [f"data changed since freeze: {k} ({frozen.get(k, '-')[:12]} -> {v[:12]})"
                   for k, v in now.items() if frozen.get(k) != v]
        issues += [f"frozen data missing: {k}" for k in frozen.keys() - now.keys()]
    else:
        issues.append("data/DIGESTS.json missing: run `python -m evals.retrieval freeze`")
    return issues


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.retrieval", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="integrity and digest checks")
    sub.add_parser("freeze", help="write data/DIGESTS.json from the current data")
    r = sub.add_parser("run", help="score every system")
    r.add_argument("--splits", default="dev,limits", help=f"comma-separated: {', '.join(SPLITS)}")
    r.add_argument("--systems", default=",".join(SYSTEMS))
    r.add_argument("--write", action="store_true", help="write results/summary.md, per_query.jsonl, run.json")
    args = p.parse_args(argv)

    if args.command == "freeze":
        DIGESTS_FILE.write_text(json.dumps(digests(load_queries()), indent=2) + "\n", encoding="utf-8")
        print(DIGESTS_FILE.read_text(encoding="utf-8"), end="")
        return 0
    issues = check()
    if args.command == "check" or issues:
        print("\n".join(issues) or "data OK")
        return 1 if issues else 0

    splits = tuple(s for s in args.splits.split(",") if s)
    systems = tuple(s for s in args.systems.split(",") if s)
    if BASELINE not in systems:
        systems = (BASELINE, *systems)
    queries = [q for q in load_queries() if q.split in splits]
    records = rank_all(queries, systems)
    summary = summarize(records, systems)
    lines = read_lines(summary)
    second = secondary(records, queries, systems)
    report = render(records, summary, lines, queries, systems, second)
    print(report)
    if args.write:
        RESULTS.mkdir(exist_ok=True)
        (RESULTS / "summary.md").write_text(report, encoding="utf-8")
        with open(RESULTS / "per_query.jsonl", "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        run = {"environment": environment(), "digests": digests(load_queries()), "splits": list(splits),
               "systems": list(systems), "summary": summary, "lines": lines,
               "secondary_same_team": {"summary": second[0], "lines": second[1]}}
        (RESULTS / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
