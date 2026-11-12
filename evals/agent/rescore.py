"""Re-score saved runs with matcher v2 (``matcher2.py``), offline and without any model call.

For each haystack the workspace is rebuilt session by session exactly as it was (agent cells: the logged
writes replayed through the MCP server, final attempt of each session, with the ``@history`` cards the
harness had added; ``flat`` and ``oracle``: the harness's own ingestion), and at every judgment point the
plan's items are judged again with v2: the recorded first pages (addresses, warnings and redirects as the
run saw them), updates, deletions and current values. Which values are matchable is decided by v2 too.
Output: the same record schema as the runner, under ``<runs>/<run>-v2/``.

    python -m evals.agent.rescore --run tier1 --run gate1 --run tier1-var1 ...
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from . import matcher2 as m2
from . import plan as planmod


def _patch_plan() -> None:
    """Make the plan decide matchability with v2 (``plan`` only uses ``card_text`` and ``states``)."""
    planmod.card_text = lambda title, aliases, summary, body: m2.Text(title=title, aliases=aliases, summary=summary, body=body)
    planmod.states = lambda t, value, anchors=None: m2.states(t, value, anchors)
    planmod.states_any = lambda t, values, anchors=None: m2.states_any(t, values, anchors)


class Snapshot:
    """Card texts and lineage flags of a workspace at one point."""

    def __init__(self, ws, cache: dict) -> None:
        from mindslice.model.card import parse_card
        from mindslice.storage.card_io import read_card_file

        from .judge import Judge

        j = Judge(ws)
        j.refresh()
        self.flags = j.flags(j.addresses())
        self.text: dict[str, m2.Text] = {}
        for a, row in j._rows.items():
            key = (a, row["mtime_ns"], row["size"])
            if key not in cache:
                raw, _ = read_card_file(j._roots[row["mount"]] / f"{row['path']}.md")
                p = parse_card(raw or "")
                cache[key] = m2.Text(title=p.display_title(row["path"]), aliases=p.aliases, summary=p.summary, body=p.body)
            self.text[a] = cache[key]

    def active(self, a: str) -> bool:
        return self.flags.get(a, (False, True))[0]

    def unwarned(self, a: str) -> bool:
        f = self.flags.get(a, (False, True))
        return f[0] and not f[1]


def rescore_haystack(hdir: Path, out: Path, data: str | None) -> int:
    from evals.external.datasets import LOADERS
    from evals.external.harness import _apply_lineage
    from mindslice import Workspace
    from mindslice.interfaces.mcp_server import MCPServer

    from .agents import SessionTask, make
    from .runner import HISTORY_ALIAS, HISTORY_ARMS, LINEAGE_ARMS, write_history
    from .sessions import agent_sessions, flat

    _patch_plan()
    recs = [json.loads(l) for l in (hdir / "records.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if not recs or recs[0].get("kind") == "deferred":
        return 0
    arm, key, dataset = recs[0]["arm"], recs[0]["haystack"], recs[0]["dataset"]
    h = next(x for x in LOADERS[dataset](Path(data) if data else None) if x.key == key)
    b_eval = flat(h)
    sessions = agent_sessions(h, b_eval)
    pl = planmod.build(h, b_eval, sessions)
    others = sorted({f["value"] for f in h.info.get("timeline", [])})
    pages = {(r["id"], str(r["point"])): r for r in recs if r["kind"] == "question"}
    base = {"arm": arm, "dataset": dataset, "haystack": key}
    out_recs = [r for r in recs if r["kind"] in ("session", "haystack")]
    cache: dict = {}
    with tempfile.TemporaryDirectory(prefix="ms-rescore-") as tmp:
        ws = Workspace.init(Path(tmp) / "ws")
        try:
            if arm in HISTORY_ARMS:
                hist = ws.root / "history.slice"
                hist.mkdir()
                ws.mount(hist, alias=HISTORY_ALIAS, role="baseline")
            if arm.startswith("agent-"):
                rows = [json.loads(l) for l in (hdir / "calls.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
                rows = [r for r in rows if r.get("kind") == "tools/call" and r.get("tool") == "write" and not r.get("refused")]
                final: dict[int, int] = {}
                for r in rows:
                    final[r["session"]] = max(final.get(r["session"], 0), r.get("attempt", 0))
                server = MCPServer(ws)

                def run_session(i: int) -> None:
                    if arm in HISTORY_ARMS:
                        write_history(ws.root / "history.slice", sessions[i].cards)
                    for r in rows:
                        if r["session"] == i and r.get("attempt", 0) == final.get(i):
                            server._tools_call({"name": "write", "arguments": r["arguments"]})
            else:
                b_arm = flat(h)
                deletes = _apply_lineage(h, b_arm)[0] if arm in LINEAGE_ARMS and h.lineage is not None else {}
                arm_sessions = agent_sessions(h, b_arm)
                agent = make(arm)

                def run_session(i: int) -> None:
                    s = arm_sessions[i]
                    agent.run_session(SessionTask(arm, h, s, "", "", ws, Path(tmp), deletes))

            n_done = max(r["session"] for r in recs if r["kind"] == "session") + 1
            for i in range(n_done):
                run_session(i)
                snap = Snapshot(ws, cache)
                out_recs += judge_point(snap, h, pl, i, pages, base, others)
            if not any(r["kind"] == "haystack" and r.get("failed") for r in recs):
                out_recs += judge_point(snap, h, pl, planmod.END, pages, base, others)
        finally:
            ws.close()
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "records.jsonl", "w", encoding="utf-8") as fh:
        for r in out_recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(out_recs)


def judge_point(snap: Snapshot, h, pl, point, pages: dict, base: dict, others: list[str]) -> list[dict[str, Any]]:
    out = []
    for q in pl.questions.get(point, []):
        old = pages.get((q.id, str(point)))
        if old is None:
            continue
        m = pl.matchable[q.id]
        vals = q.meta.get("values", {})
        cur_all = vals.get("current", [])
        anc = vals.get("anchors") or None
        page = []
        for r in old["page"]:
            t = snap.text.get(r["address"])
            via_hist: set[int] = set()
            for v in r.get("via", []):
                vt = snap.text.get(v)
                if vt is not None:
                    via_hist |= {j for j, x in enumerate(m["history"]) if m2.states(vt, x, anc)}
            if t is None:
                page.append({**r, "stale": False, "current": False, "current_values": [], "history": [], "via_history": sorted(via_hist)})
                continue
            page.append({**r, "stale": m2.is_stale(t, m["stale"], cur_all, others, anc),
                         "current": m2.states_any(t, m["current"], anc),
                         "current_values": [j for j, x in enumerate(m["current"]) if m2.states(t, x, anc)],
                         "history": [j for j, x in enumerate(m["history"]) if m2.states(t, x, anc)],
                         "via_history": sorted(via_hist)})
        out.append({**old, "matchable": m, "page": page, "matcher": "v2"})
    for v in pl.values.get(point, []):
        anc = v.anchors or None  # kept only where presented as current
        holders = [a for a, t in snap.text.items() if snap.active(a) and m2.states_current(t, v.value, anc)] if v.matchable else []
        out.append({**base, "kind": "value", "id": v.id, "point": point, "category": v.category, "value": v.value,
                    "entity": v.entity, "matchable": v.matchable, "lost": (not holders) if v.matchable else None,
                    "holders": holders[:5]})
    if isinstance(point, int):
        for u in pl.updates.get(point, []):
            offenders = [a for a, t in snap.text.items() if snap.unwarned(a) and m2.is_stale(t, u.stale, u.current, others, u.anchors or None)] \
                if u.matchable else []
            out.append({**base, "kind": "update", "id": u.id, "update_kind": u.kind, "session": point, "stale": u.stale,
                        "current": u.current, "matchable": u.matchable, "retired": (not offenders) if u.matchable else None,
                        "offenders": offenders[:5]})
        for d in pl.deletions.get(point, []):
            offenders = [a for a, t in snap.text.items() if snap.active(a) and m2.states_any(t, d.values)] if d.values else []
            out.append({**base, "kind": "deletion", "id": d.id, "entity": d.entity, "session": point, "values": d.values,
                        "matchable": bool(d.values), "forgotten": (not offenders) if d.values else None, "offenders": offenders[:5]})
    return out


def _job(args) -> tuple[str, int]:
    hdir, out, data = args
    try:
        return str(hdir), rescore_haystack(Path(hdir), Path(out), data)
    except Exception as exc:  # report and go on
        return f"ERROR {hdir}: {type(exc).__name__}: {exc}", -1


def main(argv=None) -> int:
    from evals.external import sources

    from .run import TIER1_DROPPED, runs_root, slug

    p = argparse.ArgumentParser(prog="python -m evals.agent.rescore")
    p.add_argument("--run", action="append", required=True)
    p.add_argument("--arms", help="comma-separated arm directories (default: all)")
    p.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    p.add_argument("--include-dropped", action="store_true", help="also re-score tier 1's dropped haystack (validation)")
    p.add_argument("--suffix", default="-v2")
    args = p.parse_args(argv)
    root = runs_root()
    data = str(sources.data_dir(None))
    dropped = {slug(k) for k in TIER1_DROPPED}
    work = []
    for run in args.run:
        for arm in sorted(d for d in (root / run).iterdir() if d.is_dir()):
            if args.arms and arm.name not in args.arms.split(","):
                continue
            for hdir in sorted(d for d in arm.iterdir() if d.is_dir() and (d / "records.jsonl").exists()):
                if run.startswith(("tier1", "gate1")) and hdir.name in dropped and not args.include_dropped:
                    continue
                work.append((str(hdir), str(root / f"{run}{args.suffix}" / arm.name / hdir.name), data))
    bad = 0
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for i, f in enumerate(as_completed([pool.submit(_job, w) for w in work]), 1):
            name, n = f.result()
            if n < 0:
                bad += 1
                print(name, file=sys.stderr)
            if i % 100 == 0 or i == len(work):
                print(f"{i}/{len(work)}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
