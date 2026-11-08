"""Every hand verdict of the audits as ground truth, and a re-scored run's agreement with it.

Sources, later ones overriding earlier ones for the same case: the tier-1 audit (``results/audit/tier1/``,
frozen matcher), the v2 audit (``results/audit/tier1-v2/``: flagged cases, passes, flips), the Absence
sample (``results/audit/tier1-v2/absence/``), the v3 worksheets (``results/audit/tier1-v3/``) and the fresh
labels judged for v3's changes (``results/audit/tier1-v3/fresh/``).
A verdict says what is true of the workspace, whatever matcher flagged the case:

* ``update``: retired (a flagged failure judged a matching error, or a pass judged correct) or not;
* ``value``: lost (a flagged case judged correct) or kept;
* ``question`` (Absence pages): an unwarned stale card on the first page or not.

    python -m evals.agent.labels --run tier1-v3
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

RESULTS = Path(__file__).resolve().parent / "results" / "audit"


def _key(cell: str, kind: str, case: dict) -> tuple:
    return (cell, kind, case["id"], str(case.get("point", case.get("session"))))


def truths(root: Path = RESULTS) -> dict[tuple, dict[str, Any]]:
    out: dict[tuple, dict[str, Any]] = {}

    def put(cell, kind, case, truth, source):
        out[_key(cell, kind, case)] = {"cell": cell, "kind": kind, "id": case["id"],
                                       "point": case.get("point", case.get("session")), "truth": truth, "source": source}

    for d, src in ((root / "tier1", "tier1 audit"), (root / "tier1-v2", "v2 audit"), (root / "tier1-v3", "v3 audit"),
                   (root / "tier1-v3" / "fresh", "v3 fresh")):
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            ws = json.loads(f.read_text(encoding="utf-8"))
            cases = ws.get("cases", {})
            if not isinstance(cases, dict):
                continue
            for c in cases.get("retired", []):
                if c.get("verdict") in ("correct", "matching error"):
                    put(f.stem, "update", c, c["verdict"] == "matching error", src + " (flagged)")
            for c in cases.get("passes", []):
                if c.get("verdict") in ("correct", "missed"):
                    put(f.stem, "update", c, c["verdict"] == "correct", src + " (passes)")
            for c in cases.get("lost", []):
                if c.get("verdict") in ("correct", "matching error"):
                    put(f.stem, "value", c, c["verdict"] == "correct", src + " (flagged)")
            for c in cases.get("flips", []) + cases.get("kept", []):
                if c.get("verdict") in ("correct", "missed", "matching error"):
                    put(f.stem, "value", c, c["verdict"] != "correct", src + " (kept)")
            for c in cases.get("absence_clean", []):
                if c.get("verdict") in ("correct", "missed"):
                    put(f.stem, "question", c, c["verdict"] == "missed", src + " (Absence, clean)")
        a = d / "absence"
        for f in sorted(a.glob("*.json")) if a.is_dir() else []:
            ws = json.loads(f.read_text(encoding="utf-8"))
            for c in ws["cases"]:
                if c.get("verdict") in ("correct", "matching error"):
                    put(ws["cell"], "question", c, c["verdict"] == "correct", src + " (Absence)")
    return out


def judged(run_dir: Path, cell: str) -> dict[tuple, Any]:
    """What a run's records say for every case kind, keyed like ``truths``."""
    out: dict[tuple, Any] = {}
    for h in sorted((run_dir / cell).iterdir()):
        p = h / "records.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["kind"] == "update":
                out[(cell, "update", r["id"], str(r["session"]))] = r["retired"]
            elif r["kind"] == "value":
                out[(cell, "value", r["id"], str(r["point"]))] = r["lost"]
            elif r["kind"] == "question":
                out[(cell, "question", r["id"], str(r["point"]))] = any(x["stale"] and not x["warned"] for x in r["page"][:10])
    return out


def agreement(run_dir: Path, root: Path = RESULTS) -> dict[str, Any]:
    t = truths(root)
    cells = sorted({k[0] for k in t})
    got: dict[tuple, Any] = {}
    for c in cells:
        if (run_dir / c).is_dir():
            got.update(judged(run_dir, c))
    rows: dict[tuple, dict[str, Any]] = defaultdict(lambda: {"n": 0, "agree": 0, "unmatchable": 0, "missing": 0, "wrong": []})
    for k, v in sorted(t.items()):
        e = rows[(v["kind"], v["source"])]
        if k not in got:
            e["missing"] += 1
            continue
        g = got[k]
        if g is None:
            e["unmatchable"] += 1
            continue
        e["n"] += 1
        if g == v["truth"]:
            e["agree"] += 1
        else:
            e["wrong"].append({"cell": k[0], "id": k[2], "point": k[3], "truth": v["truth"], "judged": g})
    return {f"{kind} / {src}": e for (kind, src), e in sorted(rows.items())}


def main(argv=None) -> int:
    from .run import runs_root

    p = argparse.ArgumentParser(prog="python -m evals.agent.labels")
    p.add_argument("--run", required=True, action="append")
    p.add_argument("--show", type=int, default=0, help="list up to N disagreements per row")
    args = p.parse_args(argv)
    for run in args.run:
        print(f"== {run}")
        for name, e in agreement(runs_root() / run).items():
            print(f"  {name:38} agree {e['agree']:3}/{e['n']:3}  unmatchable {e['unmatchable']}  missing {e['missing']}")
            for w in e["wrong"][: args.show]:
                print(f"      {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
