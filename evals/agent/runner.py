"""Run one memory writer over one haystack and judge its workspace (agent_test.md 2, 6).

A fresh workspace per haystack (one ``@overlay`` mount, empty; ``@history`` added read-only for the overlay
arms). Sessions run in order; after each one the harness (never the agent) judges what the plan
(``plan.py``) puts at that point: the benchmark questions (``search(question, k=10)``), updates, deletions,
and the values that must still be stated. Records go to ``records.jsonl`` beside the workspace, which is
kept for auditing.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from evals.external.corpus import Card
from evals.external.datasets import Haystack, Question
from evals.external.harness import _apply_lineage

from . import plan as planmod
from .agents import SessionOutcome, SessionTask, make
from .judge import Judge, is_stale, states, states_any
from .prompts import session_message, system_prompt
from .sessions import agent_sessions, flat
from .tools import CAP, Dispatcher, JsonlLog, summarize_calls

HISTORY_ARMS = ("scripted-overlay", "agent-overlay")
LINEAGE_ARMS = ("oracle", "scripted-oracle", "scripted-overlay")
CARD_LEVEL_ARMS = ("flat", "oracle", "scripted-flat", "scripted-oracle", "scripted-overlay")
HISTORY_ALIAS = "@history"


def canonical(address: str) -> str:
    """Map an overlay arm's addresses onto Mode B's (for card-level diagnostics only)."""
    if address.startswith(HISTORY_ALIAS + "/"):
        return "@overlay/" + address.split("/", 1)[1]
    if address.startswith("@overlay/lineage/"):
        return "@overlay/" + address[len("@overlay/lineage/"):]
    return address


def write_history(root: Path, cards: list[Card]) -> None:
    for card in cards:
        target = root / f"{card.path}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(card.render(), encoding="utf-8")
        tmp.replace(target)


def run_haystack(h: Haystack, arm: str, out: Path, agent=None, cap: int | None = CAP, keep_index: bool = False,
                 log=lambda s: None) -> list[dict[str, Any]]:
    from mindslice import Workspace

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    b_eval = flat(h)
    sessions = agent_sessions(h, b_eval)
    pl = planmod.build(h, b_eval, sessions)
    b_arm = flat(h)
    deletes: dict[str, list[str]] = {}
    if arm in LINEAGE_ARMS and h.lineage is not None:
        deletes, _ = _apply_lineage(h, b_arm)
    arm_sessions = agent_sessions(h, b_arm)
    agent = agent or make(arm)
    ws = Workspace.init(out / "ws")
    history = None
    if arm in HISTORY_ARMS:
        history = ws.root / "history.slice"
        history.mkdir()
        ws.mount(history, alias=HISTORY_ALIAS, role="baseline")
    judge = Judge(ws)
    calls = JsonlLog(out / "calls.jsonl")
    records: list[dict[str, Any]] = []
    base = {"arm": arm, "dataset": h.dataset, "haystack": h.key}
    sys_prompt = system_prompt(arm)
    failed = None
    try:
        for i, s in enumerate(arm_sessions):
            if history is not None:
                write_history(history, sessions[i].cards)
            msg = session_message(i + 1, s.total, s.date, s.transcript)
            task = SessionTask(arm, h, s, sys_prompt, msg, ws, out, deletes)
            dispatch = Dispatcher(ws, calls, i, cap if not arm.startswith("scripted") else None, haystack=h.key, arm=arm)
            t0 = time.time()
            outcome: SessionOutcome = agent.run_session(task, dispatch if getattr(agent, "tools", True) else None)
            wall = time.time() - t0
            rows = outcome.calls if outcome.calls else _rows_of(out / "calls.jsonl", i) if getattr(agent, "tools", True) else []
            records.append({**base, "kind": "session", "session": i, "sessions": s.total, "wall_s": round(wall, 3),
                            "reply": outcome.reply, "failed": outcome.failed, **summarize_calls(rows), **outcome.meta})
            if outcome.failed:
                failed = f"session {i}: {outcome.meta.get('error', 'failed')}"
                break
            judge.refresh()
            records += judge_point(judge, h, pl, i, arm, base, b_eval)
            log(f"{h.key} {arm} session {i + 1}/{s.total} {wall:.1f}s")
        if failed is None:
            records += judge_point(judge, h, pl, planmod.END, arm, base, b_eval)
        records.append({**base, "kind": "haystack", "failed": failed, "cards": _card_counts(judge)})
    finally:
        calls.close()
        ws.close()
        if not keep_index:
            shutil.rmtree(ws.root / ".cache", ignore_errors=True)
    with open(out / "records.jsonl", "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return records


def _rows_of(path: Path, session: int) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [r for r in (json.loads(l) for l in fh if l.strip()) if r.get("session") == session]


def _card_counts(judge: Judge) -> dict[str, int]:
    judge.refresh()
    out: dict[str, int] = {}
    for a in judge.addresses():
        mount = a.split("/", 1)[0]
        out[mount] = out.get(mount, 0) + 1
    return out


def judge_point(judge: Judge, h: Haystack, pl: planmod.Plan, point, arm: str, base: dict, b) -> list[dict[str, Any]]:
    out = []
    for q in pl.questions.get(point, []):
        out.append(ask(judge, h, q, pl.matchable[q.id], arm, base, point, b))
    for v in pl.values.get(point, []):
        holders = judge.active_stating([v.value], v.anchors or None) if v.matchable else []
        out.append({**base, "kind": "value", "id": v.id, "point": point, "category": v.category, "value": v.value, "entity": v.entity,
                    "anchors": v.anchors, "matchable": v.matchable, "lost": (not holders) if v.matchable else None,
                    "holders": holders[:5]})
    if isinstance(point, int):
        for u in pl.updates.get(point, []):
            offenders = judge.active_stale(u.stale, u.current, u.anchors or None) if u.matchable else []
            out.append({**base, "kind": "update", "id": u.id, "update_kind": u.kind, "session": point, "stale": u.stale,
                        "current": u.current, "anchors": u.anchors, "matchable": u.matchable,
                        "retired": (not offenders) if u.matchable else None, "offenders": offenders[:5]})
        for d in pl.deletions.get(point, []):
            offenders = judge.active_stating(d.values) if d.values else []
            out.append({**base, "kind": "deletion", "id": d.id, "entity": d.entity, "session": point, "values": d.values,
                        "matchable": bool(d.values), "forgotten": (not offenders) if d.values else None,
                        "offenders": offenders[:5]})
    return out


def ask(judge: Judge, h: Haystack, q: Question, m: dict[str, list[str]], arm: str, base: dict, point, b) -> dict[str, Any]:
    page, res = judge.page(q.text)
    vals = q.meta.get("values", {})
    anchors = vals.get("anchors") or None
    current_all = vals.get("current", [])
    results = []
    for r in page:
        t = judge.text(r["address"])
        if t is None:
            results.append({**r, "stale": False, "current": False, "history": [], "via_history": []})
            continue
        via_hist: set[int] = set()
        for v in r["via"]:
            vt = judge.text(v)
            if vt is not None:
                via_hist |= {j for j, x in enumerate(m["history"]) if states(vt, x)}
        results.append({**r, "stale": is_stale(t, m["stale"], current_all, anchors),
                        "current": states_any(t, m["current"], anchors),
                        "current_values": [j for j, x in enumerate(m["current"]) if states(t, x, anchors)],
                        "history": [j for j, x in enumerate(m["history"]) if states(t, x)],
                        "via_history": sorted(via_hist)})
    rec = {**base, "kind": "question", "id": q.id, "category": q.category, "point": point,
           "task": q.meta.get("task"), "phase": q.meta.get("phase"), "hop": q.meta.get("hop"),
           "conflict": bool(vals.get("stale")) if h.dataset == "mab-sh" else None,
           "query": q.text, "values": {k: v for k, v in vals.items()}, "matchable": m, "page": results,
           "unmatched_terms": res["unmatched_terms"], "total_matches": res["total_matches"]}
    if arm in CARD_LEVEL_ARMS:
        ranked = [canonical(r["address"]) for r in page]
        card = {"ranked": ranked, "warned": [r["warned"] for r in page],
                "via": [[canonical(v) for v in r["via"]] for r in page]}
        for key in ("current", "stale", "history"):
            if key in q.meta:
                card[key] = b.addresses(q.meta[key])
        rec["card"] = card
    return rec
