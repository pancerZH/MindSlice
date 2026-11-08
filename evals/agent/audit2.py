"""The 6.3 audit for matcher v2, both ways (post-hoc re-score and the confirmatory run).

* **Flagged** (as 6.3): up to 50 of v2's ``retired`` failures and 50 of its ``lost`` cases per cell (seed
  20261106), with the exact lines v2 acted on. Cases already judged in the tier-1 audit keep their verdict.
* **Passes** (the direction 6.3 doesn't cover): updates v2 counts as retired, with every statement line of an
  active, unwarned card that shares a word with the old value; and values v2 keeps that the frozen matcher had
  called lost, with the line v2 found them on.

Evidence is the workspace at the judgment point, replayed from the logged writes (``audit.replay``).
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path
from typing import Any

from . import audit
from . import matcher2 as m2

SEED = 20261106


def _snapshot(hdir: Path, point) -> dict[str, tuple[bool, m2.Text, str]]:
    if point == "end":
        point = max(x["session"] for x in audit._records(hdir) if x["kind"] == "session")
    with tempfile.TemporaryDirectory() as t:
        cards = audit.replay(hdir, int(point), Path(t))
    return {a: (not txt.startswith("[INACTIVE] "), m2.Text(txt.removeprefix("[INACTIVE] ")), txt) for a, txt in cards.items()}


def _others(key: str, data) -> list[str]:
    from evals.external.datasets import LOADERS

    ds = key.split("/", 1)[0]
    h = next(x for x in LOADERS[ds](data) if x.key == key)
    return sorted({f["value"] for f in h.info.get("timeline", [])})


def worksheet(cell_dir: Path, orig_dir: Path, labels: dict | None, data=None, n_flag: int = 50, n_pass: int = 15,
              n_flip: int = 20, v1_dir: Path | None = None) -> dict[str, Any]:
    recs = {h.name: audit._records(h) for h in sorted(cell_dir.iterdir()) if (h / "records.jsonl").exists()}
    lab_r = {c["id"]: c for c in (labels or {}).get("retired", []) if c.get("verdict")}
    lab_l = {(c["id"], str(c["point"])): c for c in (labels or {}).get("lost", []) if c.get("verdict")}
    fail = [(h, r) for h, rs in recs.items() for r in rs if r["kind"] == "update" and r["retired"] is False]
    lost = [(h, r) for h, rs in recs.items() for r in rs if r["kind"] == "value" and r["lost"] is True]
    passed = [(h, r) for h, rs in recs.items() for r in rs if r["kind"] == "update" and r["retired"] is True]
    flips = []
    if v1_dir is not None:
        for h in recs:
            v1 = {(r["id"], str(r["point"])) for r in audit._records(v1_dir / h) if r["kind"] == "value" and r["lost"] is True}
            flips += [(h, r) for r in recs[h] if r["kind"] == "value" and r["lost"] is False and (r["id"], str(r["point"])) in v1
                      and (r["id"], str(r["point"])) not in lab_l]
    key = lambda hr: (hr[0], hr[1]["id"], str(hr[1].get("point", hr[1].get("session"))))
    pick = lambda pool, n: random.Random(SEED).sample(sorted(pool, key=key), min(n, len(pool)))
    out: dict[str, Any] = {"cell": cell_dir.name, "population": {"retired": len(fail), "lost": len(lost), "passes": len(passed),
                                                                  "flips": len(flips)}, "cases": {}}
    cache: dict = {}

    def snap(h, point):
        k = (h, str(point))
        if k not in cache:
            cache[k] = _snapshot(orig_dir / h, point)
        return cache[k]

    rows = []
    for h, r in pick(fail, n_flag):
        old = lab_r.get(r["id"])
        s = snap(h, r["session"])
        others = _others(r["haystack"], data)
        ev = {}
        for a in r["offenders"][:3]:
            t = s[a][1]
            ev[a] = [ln for ln, al in zip(t.lines, t.is_alias)
                     if not al and any(m2.presents_old(m2.Text(ln), v, others) for v in r["stale"])][:3]
        rows.append({"id": r["id"], "dir": h, "session": r["session"], "stale": r["stale"], "current": r["current"], "evidence": ev,
                     "verdict": old["verdict"] if old else None, "note": ("from the tier-1 audit" if old else "")})
    out["cases"]["retired"] = rows
    rows = []
    for h, r in pick(lost, n_flag):
        old = lab_l.get((r["id"], str(r["point"])))
        s = snap(h, r["point"])
        req = set(m2.value_parts(r["value"])[0]) | set(m2.tokens(str(r.get("entity", "")).replace("_", " ")))
        req -= {"user", "my"}
        near = {a + ("" if act else " (inactive)"): [ln for ln in t.lines if set(m2.tokens(ln)) & req][:3]
                for a, (act, t, _) in s.items() if t.token_set & req}
        near = dict(sorted(near.items(), key=lambda kv: -max((len(set(m2.tokens(l)) & req) for l in kv[1]), default=0))[:5])
        rows.append({"id": r["id"], "dir": h, "point": r["point"], "value": r["value"], "entity": r.get("entity"), "near": near,
                     "verdict": old["verdict"] if old else None, "note": ("from the tier-1 audit" if old else "")})
    out["cases"]["lost"] = rows
    rows = []
    for h, r in pick(passed, n_pass):
        s = snap(h, r["session"])
        words = set().union(*(set(m2.value_parts(v)[0]) for v in r["stale"]))
        ev = {a: [ln for ln, al in zip(t.lines, t.is_alias) if not al and set(m2.tokens(ln)) & words][:3]
              for a, (act, t, _) in s.items() if act and t.token_set & words}
        ev = {a: l for a, l in ev.items() if l}
        rows.append({"id": r["id"], "dir": h, "session": r["session"], "stale": r["stale"], "current": r["current"],
                     "evidence": dict(list(ev.items())[:5]), "verdict": None, "note": ""})
    out["cases"]["passes"] = rows
    rows = []
    for h, r in pick(flips, n_flip):
        s = snap(h, r["point"])
        hold = {a: [ln for ln in s[a][1].lines if m2.states_current(m2.Text(ln), r["value"])][:2] or s[a][1].lines[:2]
                for a in r["holders"][:2] if a in s}
        rows.append({"id": r["id"], "dir": h, "point": r["point"], "value": r["value"], "holders": hold, "verdict": None, "note": ""})
    out["cases"]["flips"] = rows
    return out


def tally(ws: dict[str, Any]) -> dict[str, Any]:
    """Flagged: share of matching errors (6.3). Passes and flips: share where v2 was wrong."""
    out = {}
    for kind, rows in ws["cases"].items():
        judged = [r for r in rows if r.get("verdict")]
        bad = sum(1 for r in judged if r["verdict"] in ("matching error", "missed"))
        out[kind] = {"judged": len(judged), "errors": bad, "matching_errors": bad,
                     "share": round(bad / len(judged), 3) if judged else None}
    out["reliable"] = all((v["share"] or 0) <= 0.20 for k, v in out.items() if k in ("retired", "lost"))
    return out


def corrected(records: list[dict[str, Any]], ws: dict[str, Any]) -> dict[str, Any]:
    """``retired`` and ``lost`` corrected both ways (not a pre-registered line).

    Flagged cases judged matching errors come out (exactly when every flagged case was judged, else at the
    sample's share); misses come in at the share of the passes sample (``retired``: updates v2 counted as
    retired that weren't) and of the flips sample (``lost``: values the frozen matcher called lost, v2 kept,
    and v2 was wrong). No hand-labelled case of the tier-1 audit is judged the other way by v2, so none is
    added exactly. Values both matchers keep are not audited."""
    t = tally(ws)
    pop = ws["population"]
    out: dict[str, Any] = {}
    for kind, key, other in (("retired", "update", "passes"), ("lost", "value", "flips")):
        units = [r for r in records if r["kind"] == key and r.get("matchable")]
        n = len(units)
        flagged = sum(1 for r in units if r.get(kind) is (kind == "lost"))
        f, o = t.get(kind, {}), t.get(other, {})
        exact = f.get("judged", 0) == flagged
        true_bad = flagged - f.get("errors", 0) if exact else flagged * (1 - (f.get("share") or 0))
        miss = pop.get(other, 0) * (o.get("share") or 0)
        bad = true_bad + miss
        out[kind] = {"n": n, "flagged": flagged, "audited": f.get("judged", 0), "matching_errors": f.get("errors", 0),
                     "other_population": pop.get(other, 0), "other_audited": o.get("judged", 0), "other_errors": o.get("errors", 0),
                     "raw": round((1 - flagged / n) if kind == "retired" else flagged / n, 4) if n else None,
                     "corrected": round((1 - bad / n) if kind == "retired" else bad / n, 4) if n else None, "exact": exact}
    return out
