"""The manual audit of value matching (agent_test.md 6.3): worksheets and their verdicts.

For each agent arm (and model), a fixed random sample (seed 20261106) of up to 50 ``retired`` failures and
50 ``lost`` cases, each with the evidence an auditor needs from the saved workspace:

* a ``retired`` failure: the offending active, unwarned cards and the lines that state the stale value, and
  whether any card states the current value;
* a ``lost`` case: the active cards sharing a distinctive word with the value (where a paraphrase would be).

Evidence comes from the workspace as it was at the judgment point (after the update's session, or at the
question point), rebuilt by replaying the agent's logged writes (``replay``), not from the final files.

The auditor marks each case ``correct`` (the matcher's judgment holds) or ``matching error`` (a paraphrase
missed, or a mention that doesn't present the value as current), in ``results/audit/<arm>@<model>.json``.
More than 20% matching errors in either sample means the lines are reported as unreliable.
"""

from __future__ import annotations

import json
import random
import re
import tempfile
from pathlib import Path
from typing import Any

from evals.external.datasets import normalize_text, words

from .judge import card_text, contains, states

SEED = 20261106
SAMPLE = 50
STOP = frozenset("a an and as at by for from in is of on s that the to was with my i you your it this".split())


def _cards(ws: Path) -> dict[str, tuple[bool, str]]:
    """address -> (text) for every card file in the workspace's mounts (overlay and history)."""
    from mindslice.card import parse_card

    out = {}
    for alias, sub in (("@overlay", "overlay"), ("@history", "history.slice")):
        root = ws / sub
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.md")):
            if p.name.endswith(".tmp"):
                continue
            path = p.relative_to(root).with_suffix("").as_posix()
            parsed = parse_card(p.read_text(encoding="utf-8"))
            text = "\n".join([parsed.display_title(path), *parsed.aliases, parsed.summary, parsed.body])
            out[f"{alias}/{path}"] = text
    return out


def replay(hdir: Path, upto: int, tmp: Path) -> dict[str, str]:
    """The workspace as it was right after session ``upto``: every successful ``write`` the agent made (the
    final attempt of each session only), replayed in order through the MCP server into a fresh workspace,
    with the ``@history`` cards the harness had added by then. Returns address -> card text."""
    from evals.external.datasets import LOADERS
    from mindslice import Workspace
    from mindslice.mcp_server import MCPServer

    from .runner import HISTORY_ARMS, HISTORY_ALIAS, write_history
    from .sessions import agent_sessions

    recs = [json.loads(l) for l in (hdir / "records.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    arm, key = recs[0]["arm"], recs[0]["haystack"]
    rows = [json.loads(l) for l in (hdir / "calls.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("kind") == "tools/call" and r.get("tool") == "write" and not r.get("refused")]
    final = {}
    for r in rows:
        final[r["session"]] = max(final.get(r["session"], 0), r.get("attempt", 0))
    ws = Workspace.init(tmp / "ws")
    try:
        sessions = None
        if arm in HISTORY_ARMS:
            h = next(x for x in LOADERS[recs[0]["dataset"]](None) if x.key == key)
            sessions = agent_sessions(h)
            hist = ws.root / "history.slice"
            hist.mkdir()
            ws.mount(hist, alias=HISTORY_ALIAS, role="baseline")
        server = MCPServer(ws)
        for i in range(upto + 1):
            if sessions is not None:
                write_history(ws.root / "history.slice", sessions[i].cards)
            for r in rows:
                if r["session"] == i and r.get("attempt", 0) == final.get(i):
                    server._tools_call({"name": "write", "arguments": r["arguments"]})
        ws.manifest(limit=1)
        from .judge import Judge

        judge = Judge(ws)
        judge.refresh()
        flags = judge.flags(judge.addresses())
    finally:
        ws.close()
    cards = _cards(tmp / "ws")
    # Inactive (superseded) cards are marked: a value only they state counts as lost.
    return {a: (t if flags.get(a, (True, False))[0] else "[INACTIVE] " + t) for a, t in cards.items()}


def _lines_with(text: str, needles: list[str]) -> list[str]:
    out = []
    for line in text.split("\n"):
        n = normalize_text(line)
        if n and any(contains(n, v) for v in needles):
            out.append(line.strip()[:300])
    return out


def _records(hdir: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in (hdir / "records.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def worksheet(arm_path: Path, seed: int = SEED, n: int = SAMPLE) -> dict[str, Any]:
    cases: dict[str, list[dict[str, Any]]] = {"retired": [], "lost": []}
    for hdir in sorted(p for p in arm_path.iterdir() if p.is_dir()):
        f = hdir / "records.jsonl"
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["kind"] == "update" and r.get("retired") is False:
                cases["retired"].append({"dir": hdir.name, **r})
            elif r["kind"] == "value" and r.get("lost") is True:
                cases["lost"].append({"dir": hdir.name, **r})
    out: dict[str, Any] = {"arm": arm_path.name, "population": {k: len(v) for k, v in cases.items()}, "cases": {}}
    for kind, pool in cases.items():
        pool.sort(key=lambda r: (r["dir"], r["id"], str(r.get("point"))))
        sample = random.Random(seed).sample(pool, min(n, len(pool)))
        rows = []
        for r in sample:
            # The workspace as it was when the judgment was made (replayed from the logged writes).
            point = r["session"] if kind == "retired" else r["point"]
            if point == "end":
                point = max(x["session"] for x in _records(arm_path / r["dir"]) if x["kind"] == "session")
            with tempfile.TemporaryDirectory() as tmp:
                cards = replay(arm_path / r["dir"], int(point), Path(tmp))
            if kind == "retired":
                ev = {a: _lines_with(cards[a].removeprefix("[INACTIVE] "), r["stale"]) for a in r["offenders"] if a in cards}
                cur = [a for a, t in cards.items() if states(card_text("", [], t, ""), r["current"][0], r.get("anchors") or None)]
                rows.append({"id": r["id"], "dir": r["dir"], "update_kind": r["update_kind"], "session": r["session"],
                             "stale": r["stale"], "current": r["current"], "anchors": r.get("anchors"),
                             "offenders": ev, "cards_stating_current": cur[:5], "verdict": None, "note": ""})
            else:
                # Where a paraphrase would be: the value's words and its entity's ("commute" for "30 min").
                key = [w for w in words(r["value"] + " " + str(r.get("entity", "")).replace("_", " "))
                       if w not in STOP and len(w) > 2]
                near = {a + (" (inactive)" if t.startswith("[INACTIVE] ") else ""):
                        [l.strip()[:300] for l in t.split("\n") if set(words(l)) & set(key)][:4]
                        for a, t in cards.items() if set(words(t)) & set(key)}
                # Cards that state the value (only inactive ones can, for a lost value) come first.
                overlap = lambda a: len(set(words(" ".join(near[a]))) & set(key))
                order = sorted(near, key=lambda a: (not any(r["value"] in normalize_text(l) for l in near[a]), -overlap(a), a))
                near = {a: near[a] for a in order}
                rows.append({"id": r["id"], "dir": r["dir"], "point": r["point"], "category": r["category"], "value": r["value"],
                             "entity": r.get("entity"),
                             "anchors": r.get("anchors"), "near": dict(list(near.items())[:10]), "verdict": None, "note": ""})
        out["cases"][kind] = rows
    return out


def render(ws: dict[str, Any]) -> str:
    o = [f"# Audit worksheet: `{ws['arm']}`", "",
         f"Population: {ws['population']['retired']} `retired` failures, {ws['population']['lost']} `lost` cases; "
         f"sample seed {SEED}, up to {SAMPLE} each. Verdict per case: `correct` or `matching error`.", ""]
    for kind, rows in ws["cases"].items():
        o += [f"## {kind}", ""]
        for i, r in enumerate(rows, 1):
            if kind == "retired":
                o.append(f"{i}. `{r['id']}` ({r['update_kind']}, session {r['session']}): stale {r['stale']} -> current {r['current']}"
                         + (f", anchors {r['anchors']}" if r.get("anchors") else ""))
                for a, lines in r["offenders"].items():
                    o.append(f"   - `{a}`: " + " / ".join(f"\"{l}\"" for l in lines[:3]))
                o.append(f"   - cards stating the current value: {', '.join(r['cards_stating_current']) or 'none'}")
            else:
                o.append(f"{i}. `{r['id']}` (point {r['point']}, {r['category']}, {r.get('entity') or '?'}): value \"{r['value']}\""
                         + (f", anchors {r['anchors']}" if r.get("anchors") else ""))
                for a, lines in r["near"].items():
                    o.append(f"   - `{a}`: " + " / ".join(f"\"{l}\"" for l in lines[:2]))
                if not r["near"]:
                    o.append("   - no active card shares a distinctive word")
        o.append("")
    return "\n".join(o) + "\n"


def tally(verdicts: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for kind, rows in verdicts["cases"].items():
        judged = [r for r in rows if r.get("verdict")]
        errors = sum(1 for r in judged if r["verdict"] == "matching error")
        out[kind] = {"sampled": len(rows), "judged": len(judged), "matching_errors": errors,
                     "share": round(errors / len(judged), 3) if judged else None}
    out["reliable"] = all((v["share"] or 0) <= 0.20 for v in out.values() if isinstance(v, dict))
    return out


def set_verdicts(path: Path, kind: str, errors: dict[int, str] | None = None, correct: dict[int, str] | None = None) -> None:
    """Record verdicts by 1-based case number: the cases in ``errors`` are matching errors, those in
    ``correct`` correct; when only one dict is given, every other case gets the other verdict."""
    ws = json.loads(path.read_text(encoding="utf-8"))
    rows = ws["cases"][kind]
    errors, correct = errors or {}, correct or {}
    for i, r in enumerate(rows, 1):
        if i in errors:
            r["verdict"], r["note"] = "matching error", errors[i]
        elif i in correct:
            r["verdict"], r["note"] = "correct", correct[i]
        elif errors and not correct:
            r["verdict"] = "correct"
        elif correct and not errors:
            r["verdict"] = "matching error"
    path.write_text(json.dumps(ws, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
