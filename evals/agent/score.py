"""Metrics over the runner's records (agent_test.md 6.2), with bootstrap intervals and paired differences.

Per question (only values that are matchable count; see ``plan.py``):

* ``stale@10``: an unwarned stale card is on the first page (questions with a stale value).
* ``stale-first``: an unwarned stale card ranks above every card stating a current value (questions with
  both a stale and a current value: MEME Cascade, MemoryAgentBench conflicts).
* ``current@10``: share of the question's current values that some card on the first page states (one
  value for every pooled question, so 0 or 1 there).
* ``history-named@10`` (MEME Tracking): share of the value history stated by a card on the page or by a
  superseded card named in its ``matched_via_superseded``.

Per update ``retired``, per deletion ``forgotten``, per current value at each question point ``lost``.
Intervals: 95% percentile bootstrap over the units (questions, updates, values or deletions), 2,000
replicates, seed 20261106 (``evals.retrieval.metrics``); differences between arms paired by unit.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

from evals.external.score import mean_ci, paired_ci, state as card_state, verdict_of

QUESTION_METRICS = ("stale-first", "stale@10", "current@10", "history-named@10")
POOL_STALE = ("meme/Cas-hop1", "meme/Cas-hop2", "mab-sh/conflict")
POOL_CURRENT = ("meme/Cas-hop1", "meme/Cas-hop2", "mab-sh/conflict", "mab-sh/other", "longmemeval-s/knowledge-update")

# The suggested lines (agent_test.md 8); PLAN.md freezes the values used.
LINES = (
    {"id": "G1", "claim": "The agent's lineage cuts stale-first substantially", "stat": "stale-first, flat minus arm (paired)", "line": 0.30},
    {"id": "G2", "claim": "The agent retires most stale facts", "stat": "retired", "line": 0.70},
    {"id": "G3", "claim": "Its memory keeps the current fact findable", "stat": "current@10, arm minus flat (paired)", "line": -0.05},
    {"id": "G4", "claim": "It rarely hides a true fact", "stat": "lost, all current values (lower is better)", "line": 0.05},
    {"id": "G5", "claim": "It forgets on request", "stat": "forgotten", "line": 0.90},
)


def group(rec: dict[str, Any]) -> str | None:
    d = rec["dataset"]
    if d.startswith("meme"):
        return f"meme/{rec['category']}" if rec.get("phase") == "after" else f"meme/before-{rec['category']}"
    if d == "mab-sh":
        return "mab-sh/conflict" if rec.get("conflict") else "mab-sh/other"
    if d == "longmemeval-s":
        return f"longmemeval-s/{rec['category']}"
    return None


def question_metrics(rec: dict[str, Any]) -> dict[str, float]:
    m, page = rec["matchable"], rec["page"]
    out: dict[str, float] = {}
    first_stale = next((i for i, p in enumerate(page) if p["stale"] and not p["warned"]), math.inf)
    first_current = next((i for i, p in enumerate(page) if p["current"]), math.inf)
    if m["stale"]:
        out["stale@10"] = 1.0 if first_stale < math.inf else 0.0
        if m["current"]:
            out["stale-first"] = 1.0 if first_stale < first_current else 0.0
    if m["current"]:
        found = {j for p in page for j in p.get("current_values", [])}
        out["current@10"] = len(found) / len(m["current"])
    if m["history"]:
        named = {j for p in page for j in p["history"] + p["via_history"]}
        out["history-named@10"] = len(named) / len(m["history"])
    return out


def card_metrics(rec: dict[str, Any]) -> dict[str, float]:
    """The card-level Mode B metrics (``evals.external.score.state``) on the same page, for comparison."""
    c = rec.get("card")
    # As evals/external's state groups: every question whose compiler names stale, current or history units
    # (an empty list included), except MemoryAgentBench's non-conflicts.
    if not c or not any(k in c for k in ("stale", "current", "history")):
        return {}
    if rec["dataset"] == "mab-sh" and not (c.get("stale") and c.get("current")):
        return {}
    return card_state({**c, "history": c.get("history", [])})


def units(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Every scored unit of one arm: key -> {metric: value}. Keys are stable across arms (for pairing)."""
    out: dict[str, dict[str, float]] = {}
    for r in records:
        k = r["kind"]
        if k == "question":
            g = group(r)
            if g:
                out[f"q|{r['haystack']}|{r['id']}"] = {"_group": g, **question_metrics(r)}
        elif k == "update" and r["matchable"]:
            out[f"u|{r['id']}"] = {"_group": f"{r['dataset'].split('-')[0]}/{r['update_kind']}", "retired": float(r["retired"])}
        elif k == "value" and r["matchable"]:
            out[f"v|{r['id']}|{r['point']}"] = {"_group": f"{r['dataset'].split('-')[0]}/{r['category']}", "lost": float(r["lost"])}
        elif k == "deletion" and r["matchable"]:
            out[f"d|{r['id']}"] = {"_group": "meme/Del", "forgotten": float(r["forgotten"])}
    return out


def _select(u: dict[str, dict[str, float]], metric: str, groups: Iterable[str] | None = None) -> dict[str, float]:
    gs = set(groups) if groups is not None else None
    return {k: v[metric] for k, v in u.items() if metric in v and (gs is None or v["_group"] in gs)}


def stat(u: dict[str, dict[str, float]], metric: str, groups: Iterable[str] | None = None) -> dict[str, float]:
    vals = _select(u, metric, groups)
    return mean_ci([vals[k] for k in sorted(vals)])


def paired(a: dict[str, dict[str, float]], b: dict[str, dict[str, float]], metric: str,
           groups: Iterable[str] | None = None) -> dict[str, float]:
    """Mean of a - b over the units both arms scored, with the paired bootstrap interval."""
    va, vb = _select(a, metric, groups), _select(b, metric, groups)
    keys = sorted(set(va) & set(vb))
    out = paired_ci([va[k] for k in keys], [vb[k] for k in keys])
    out["unpaired"] = len(set(va) ^ set(vb))
    return out


POOLED = {"stale-first": POOL_STALE, "stale@10": POOL_STALE, "current@10": POOL_CURRENT,
          "retired": None, "lost": None, "forgotten": None, "history-named@10": ("meme/Tr",)}


def pooled(u: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    return {m: stat(u, m, gs) for m, gs in POOLED.items()}


def groups_table(u: dict[str, dict[str, float]]) -> dict[str, dict[str, dict[str, float]]]:
    out: dict[str, dict[str, dict[str, float]]] = {}
    for g in sorted({v["_group"] for v in u.values()}):
        metrics = sorted({m for v in u.values() if v["_group"] == g for m in v if not m.startswith("_")})
        out[g] = {m: stat(u, m, (g,)) for m in metrics}
    return out


def card_level(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    per: dict[str, dict[str, list[float]]] = {}
    for r in records:
        if r["kind"] != "question":
            continue
        g = group(r)
        cm = card_metrics(r)
        for m, x in cm.items():
            per.setdefault(g, {}).setdefault(m, []).append(x)
    return {g: {m: mean_ci(xs) for m, xs in sorted(ms.items())} for g, ms in sorted(per.items())}


def lines(arm_units: dict[str, dict[str, float]], flat_units: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    """G1-G5 for one agent arm (pooled over its tier). Verdicts as in evals/external/PLAN.md."""
    s = {
        "G1": paired(flat_units, arm_units, "stale-first", POOL_STALE),
        "G2": stat(arm_units, "retired"),
        "G3": paired(arm_units, flat_units, "current@10", POOL_CURRENT),
        "G4": stat(arm_units, "lost"),
        "G5": stat(arm_units, "forgotten"),
    }
    out = []
    for spec in LINES:
        st = s[spec["id"]]
        if spec["id"] == "G4":  # lower is better: the upper bound must clear the line
            if st.get("n", 0) == 0 or math.isnan(st["mean"]):
                v = "no data"
            elif st["high"] <= spec["line"]:
                v = "confirmed"
            elif st["mean"] <= spec["line"]:
                v = "point pass"
            else:
                v = "miss"
        else:
            v = verdict_of(st, spec["line"])
        out.append({**spec, "point": st["mean"], "low": st["low"], "high": st["high"], "n": st["n"], "verdict": v})
    return out


def telemetry(records: list[dict[str, Any]]) -> dict[str, Any]:
    sess = [r for r in records if r["kind"] == "session"]
    hay = [r for r in records if r["kind"] == "haystack"]
    if not sess:
        return {}
    calls = sorted(r["tool_calls"] for r in sess)
    ops: dict[str, int] = {}
    tools: dict[str, int] = {}
    for r in sess:
        for k, v in r.get("ops", {}).items():
            ops[k] = ops.get(k, 0) + v
        for k, v in r.get("tools", {}).items():
            tools[k] = tools.get(k, 0) + v
    walls = sorted(r["wall_s"] for r in sess)
    tok = lambda key: sum(int(r.get("usage", {}).get(key) or 0) for r in sess)
    cards = [sum(v for k, v in (h.get("cards") or {}).items() if k == "@overlay") for h in hay]
    return {
        "haystacks": len(hay), "failed_haystacks": [h["haystack"] for h in hay if h.get("failed")],
        "sessions": len(sess), "tool_calls": sum(calls), "calls_per_session_mean": round(sum(calls) / len(calls), 2),
        "calls_per_session_median": calls[len(calls) // 2], "calls_per_session_max": calls[-1],
        "tools": tools, "ops": ops,
        "writes_with_supersedes": sum(r.get("with_supersedes", 0) for r in sess),
        "writes_with_extends": sum(r.get("with_extends", 0) for r in sess),
        "tool_errors": sum(r.get("tool_errors", 0) for r in sess), "cap_hits": sum(1 for r in sess if r.get("cap_hit")),
        "non_mcp_tool_calls": sum(r.get("non_mcp_tool_calls") or 0 for r in sess),
        "non_mcp_denied": sum(r.get("non_mcp_denied") or 0 for r in sess),
        "trace_mismatches": sum(1 for r in sess if r.get("trace_matches_proxy") is False),
        "client_rejected_calls": sum(r.get("client_rejected_calls") or 0 for r in sess),
        "no_done": sum(1 for r in sess if (r.get("reply") or "").strip().rstrip(".").upper().split()[-1:] != ["DONE"]),
        "retries": sum(r.get("retries", 0) for r in sess),
        "wall_s_total": round(sum(walls), 1), "wall_s_median": walls[len(walls) // 2], "wall_s_max": walls[-1],
        "overlay_cards_per_haystack": round(sum(cards) / len(cards), 1) if cards else None,
        "input_tokens": tok("input_tokens"), "output_tokens": tok("output_tokens"),
        "thinking_tokens": tok("thinking_tokens"), "cached_tokens": tok("cached_tokens"),
    }
