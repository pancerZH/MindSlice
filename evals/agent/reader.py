"""Reader QA (PLAN.md section 11, draft): a reader model answers MEME's questions from the page ``search()`` gives it.

Not frozen. Each question's workspace is rebuilt by replaying the arm's logged writes (agent arms) or its
scripted sessions (``flat``, ``oracle``) to the question's point, as ``rescore.py`` does, and its
``search(question, k=10)`` page is checked against the page the run recorded. The reader gets the page's full
cards (dates included) with the lineage notes ``search()`` returns, and answers in a fixed JSON form, graded
without an LLM (``grade``). Readers: ``none`` (renders and checks only, no model), ``qwen`` (the local Strata
server) and any Gemini model id through ``agy`` (one fresh call per question, every tool denied, a weekly-quota
floor).

    python -m evals.agent.reader --source smoke-final --cells flat,oracle --episodes pl_001 --reader none --out DIR
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

TASKS = ("Cas", "Abs", "Del")
STATUSES = ("current", "uncertain", "removed", "unknown")
SETS = {"target": "after", "control": "before"}
K = 10
PROMPT_VERSION = "draft-2"  # draft-1: no quoted lineage targets (dry-run of 2026-11-09)

SYSTEM = """You answer a user's question about themselves using only the memory excerpts you are given. The
excerpts are what a memory search returned for the question, best match first. Each one is a stored memory
card, often a dated conversation round. Some carry lineage notes from the memory system:
- "status: superseded_by: X": this card was replaced by card X, which holds the newer version.
- "matched_via_superseded: X": this card replaced the older card X.
- "baseline_superseded_by: X": this card rests on another card that has since been replaced by X.
- "missing_baselines": this card rests on a card that was deleted.
A card a note names that is not itself among the excerpts is quoted on the line below the note.

Answer about the user's situation now, after every conversation in memory; use dates to tell older statements
from newer ones. Reply with one JSON object and nothing else:
{"status": "current" | "uncertain" | "removed" | "unknown", "value": "..."}
- "current": you know what holds now; put the answer in "value", in the memory's own words.
- "uncertain": the memory had an answer, but something it depended on has changed and nothing says what holds
  now; put the earlier answer in "value".
- "removed": the user asked for this to be forgotten; leave "value" empty.
- "unknown": the memory has nothing on it; leave "value" empty."""


def user_message(page: str, question: str) -> str:
    return f"Memory excerpts:\n\n{page}\n\nQuestion: {question}"


# ---------------------------------------------------------------------------
# Questions and workspace states
# ---------------------------------------------------------------------------


def questions(records: list[dict[str, Any]], sets=("target", "control")) -> list[dict[str, Any]]:
    """The Cascade, Absence and Deletion questions of one haystack's records, in the requested sets."""
    phases = {SETS[s]: s for s in sets}
    out = []
    for r in records:
        if r.get("kind") == "question" and r.get("task") in TASKS and r.get("phase") in phases:
            out.append({**r, "set": phases[r["phase"]]})
    return out


def replay_states(hdir: Path, data: str | None = None) -> Iterator[tuple[Any, Any]]:
    """``(point, workspace)`` after each session, then ``("end", workspace)``: the states the run judged."""
    from evals.external.datasets import LOADERS
    from evals.external.harness import _apply_lineage
    from mindslice import Workspace
    from mindslice.mcp_server import MCPServer

    from .agents import SessionTask, make
    from .runner import HISTORY_ALIAS, HISTORY_ARMS, LINEAGE_ARMS, write_history
    from .sessions import agent_sessions, flat

    recs = [json.loads(l) for l in (hdir / "records.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    arm, key, dataset = recs[0]["arm"], recs[0]["haystack"], recs[0]["dataset"]
    h = next(x for x in LOADERS[dataset](Path(data) if data else None) if x.key == key)
    sessions = agent_sessions(h, flat(h))
    with tempfile.TemporaryDirectory(prefix="ms-reader-") as tmp:
        ws = Workspace.init(Path(tmp) / "ws")
        try:
            if arm in HISTORY_ARMS:
                (ws.root / "history.slice").mkdir()
                ws.mount(ws.root / "history.slice", alias=HISTORY_ALIAS, role="baseline")
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
                    agent.run_session(SessionTask(arm, h, arm_sessions[i], "", "", ws, Path(tmp), deletes))

            n_done = max(r["session"] for r in recs if r["kind"] == "session") + 1
            for i in range(n_done):
                run_session(i)
                yield i, ws
            yield "end", ws
        finally:
            ws.close()


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------


def _fmt(v: Any) -> str:
    if isinstance(v, list):
        return ", ".join(_fmt(x) for x in v)
    if isinstance(v, dict):
        if "ref" in v:
            return f"{v['ref']} (from {v.get('source', '?')})"
        return v.get("address") or json.dumps(v, ensure_ascii=False)
    return str(v)


def lineage_notes(hit: dict[str, Any]) -> list[str]:
    notes = []
    status = hit.get("status")
    if status and status != "active":
        notes.append(f"status: {status}")
        if hit.get("competing_replacements"):
            notes.append("competing replacements: " + _fmt(hit["competing_replacements"]))
    for key in ("matched_via_superseded", "baseline_superseded_by", "missing_baselines"):
        if hit.get(key):
            notes.append(f"{key}: {_fmt(hit[key])}")
    return notes


_DATE_RE = re.compile(r"Date:\s*([^\n]+)")


def lineage_targets(hit: dict[str, Any]) -> list[str]:
    """Addresses a hit's lineage notes name: its replacements, what it replaced, its replaced baselines' successors."""
    out: list[str] = []
    for key in ("superseded_by", "matched_via_superseded", "baseline_superseded_by"):
        for a in hit.get(key) or []:
            if isinstance(a, str) and a not in out:
                out.append(a)
    return out


def quote_card(ws, address: str) -> str:
    """One line for a card a lineage note names: its date (if the body has one) and its summary."""
    try:
        card = ws.read(address, follow_supersedes=False, max_backlinks=0, max_extensions=0)
    except Exception:  # noqa: BLE001 - a vanished card is shown as such
        return f"  {address}: (not found)"
    date = _DATE_RE.search(card.get("body") or "")
    text = " ".join((card.get("summary") or card.get("body") or "").split())[:240]
    return f"  {address}" + (f" ({date.group(1).strip()})" if date else "") + f": {text}"


def render_page(ws, results: list[dict[str, Any]], expand_lineage: bool = True) -> str:
    """Each hit's full card (title, summary, body with its date line) and its lineage notes, in rank order.

    With ``expand_lineage`` (page version draft-2), a card a lineage note names that isn't on the page is quoted
    under the note (date and summary), so a reader learns *what* replaced a baseline, not only that one did.
    """
    on_page = {h["address"] for h in results}
    quoted: set[str] = set()
    blocks = []
    for i, hit in enumerate(results, 1):
        card = ws.read(hit["address"], follow_supersedes=False, max_backlinks=0, max_extensions=0)
        lines = [f"[{i}] {hit['address']}: {card['title']}"]
        notes = lineage_notes(hit)
        if notes:
            lines.append("Lineage: " + "; ".join(notes))
            if expand_lineage:
                for target in lineage_targets(hit):
                    if target not in on_page and target not in quoted:
                        quoted.add(target)
                        lines.append(quote_card(ws, target))
        for part in (card.get("summary"), card.get("body")):
            if part and part.strip():
                lines.append(part.strip())
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "(no memory matched the question)"


# ---------------------------------------------------------------------------
# Answers and grading
# ---------------------------------------------------------------------------


def parse_answer(text: str | None) -> dict[str, Any] | None:
    """The reader's ``{"status", "value"}`` object, or None if there is no valid one."""
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    candidates = [text] + re.findall(r"\{[^{}]*\}", text, flags=re.S)
    for c in candidates:
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("status") in STATUSES:
            value = obj.get("value")
            return {"status": obj["status"], "value": value if isinstance(value, str) else ("" if value is None else str(value))}
    return None


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").casefold()
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def _variants(gold: str) -> list[str]:
    out = [norm(gold)]
    bare = re.sub(r"\s*\([^)]*\)\s*$", "", gold)
    if bare != gold:
        out.append(norm(bare))
    return [v for v in out if len(v) >= 3]


def value_matches(answer: str, golds: list[str]) -> bool:
    a = norm(answer)
    if len(a) < 3:
        return False
    return any(v in a or a in v for g in golds for v in _variants(g))


def grade(q: dict[str, Any], ans: dict[str, Any] | None) -> bool:
    """PLAN.md 11.1: Cascade current + value; Absence uncertain; Deletion removed/unknown without the value;
    a control: current + value."""
    if ans is None:
        return False
    vals = q.get("values") or {}
    if q["set"] == "control":
        return ans["status"] == "current" and value_matches(ans["value"], vals.get("current") or [])
    if q["task"] == "Cas":
        return ans["status"] == "current" and value_matches(ans["value"], vals.get("current") or [])
    if q["task"] == "Abs":
        return ans["status"] == "uncertain"
    if q["task"] == "Del":
        deleted = vals.get("deleted") or vals.get("stale") or []
        return ans["status"] in ("removed", "unknown") and not value_matches(ans["value"], deleted)
    return False


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


class NoReader:
    name = "none"

    def answer(self, system: str, user: str) -> dict[str, Any]:
        return {"content": None, "latency_s": 0.0, "usage": {}}


class QwenReader:
    name = "qwen"

    def __init__(self, url: str = "http://127.0.0.1:8080", model: str = "qwen3.8-flash-next-iq3_s",
                 max_tokens: int = 4096) -> None:
        self.url, self.model, self.max_tokens = url, model, max_tokens

    def answer(self, system: str, user: str) -> dict[str, Any]:
        body = {"model": self.model, "temperature": 0, "seed": 20261106, "cache_prompt": False,
                "max_tokens": self.max_tokens, "messages": [{"role": "system", "content": system},
                                                            {"role": "user", "content": user}]}
        req = urllib.request.Request(self.url + "/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=900) as r:
            resp = json.loads(r.read())
        choice = resp["choices"][0]
        t = resp.get("timings") or {}
        return {"content": choice["message"].get("content"), "latency_s": round(time.time() - t0, 2),
                "finish_reason": choice.get("finish_reason"),
                "usage": {"prompt_tokens": t.get("prompt_n"), "generated_tokens": t.get("predicted_n"),
                          "reasoning_chars": len(choice["message"].get("reasoning_content") or "")}}


class GeminiReader:
    """One fresh ``agy --print`` conversation per question: a reader agent, no MCP server, every tool denied."""

    AGENT = "mindslice-reader"

    def __init__(self, model: str, effort: str = "medium", weekly_floor: float = 0.055, timeout_s: int = 600) -> None:
        self.name, self.model, self.effort, self.weekly_floor, self.timeout_s = model, model, effort, weekly_floor, timeout_s

    def answer(self, system: str, user: str) -> dict[str, Any]:
        from . import agy

        before = agy.read_usage()
        weekly = (before or {}).get("weekly", {}).get("remaining")
        if weekly is None or weekly < self.weekly_floor:
            raise QuotaFloor(f"weekly Gemini quota {weekly} is below the floor {self.weekly_floor}")
        with tempfile.TemporaryDirectory(prefix="ms-reader-agy-") as tmp:
            cwd = Path(tmp) / "cwd"
            (cwd / ".agents" / "agents").mkdir(parents=True)
            (cwd / ".agents" / "agents" / f"{self.AGENT}.md").write_text(
                agy.agent_markdown(system, {"name": self.AGENT, "description": "Reader for MindSlice reader QA (evals/agent)."}),
                encoding="utf-8")
            gate_log = Path(tmp) / "gate.jsonl"
            gate = (f"cd {shlex.quote(str(agy.REPO))} && {shlex.quote(sys.executable)} -m evals.agent.tool_gate "
                    f"--log {shlex.quote(str(gate_log))}")
            hooks = {"reader-tool-gate": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": gate, "timeout": 30}]}]}}
            (cwd / ".agents" / "hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
            cmd = [agy.AGY, f"--print={user}", "--model", self.model, "--effort", self.effort, "--agent", self.AGENT, *agy.FLAGS]
            t0 = time.time()
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=self.timeout_s, stdin=subprocess.DEVNULL)
            latency = round(time.time() - t0, 2)
            events = [json.loads(l) for l in proc.stdout.splitlines() if l.strip().startswith("{")]
            res = agy.result_of(events)
            denied = sum(1 for l in gate_log.read_text().splitlines() if '"deny"' in l) if gate_log.exists() else 0
        after = agy.read_usage()
        usage = res.get("usage") or {}
        return {"content": res.get("response") if isinstance(res.get("response"), str) else None, "latency_s": latency,
                "status": res.get("status"), "exit_code": proc.returncode, "tools_denied": denied,
                "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens", "thinking_tokens", "cache_read_tokens")},
                "weekly_before": weekly, "weekly_after": (after or {}).get("weekly", {}).get("remaining")}


class QuotaFloor(RuntimeError):
    pass


def make_reader(name: str, weekly_floor: float = 0.055):
    if name == "none":
        return NoReader()
    if name == "qwen":
        return QwenReader()
    if name.startswith("gemini-"):
        return GeminiReader(name, weekly_floor=weekly_floor)
    raise ValueError(f"unknown reader {name!r}")


# ---------------------------------------------------------------------------
# A run
# ---------------------------------------------------------------------------


def run(source: Path, cells: list[str], episodes: list[str], reader, out: Path, sets=("target", "control"),
        limit: int | None = None, data: str | None = None, log=print) -> list[dict[str, Any]]:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{reader.name}.jsonl"
    done = set()
    if path.exists():
        done = {(r["cell"], r["id"], str(r["point"])) for r in map(json.loads, path.read_text().splitlines()) if r.get("answered")}
    results = []
    with open(path, "a", encoding="utf-8") as fh:
        for cell in cells:
            n = 0
            for ep in episodes:
                hdir = source / cell / f"meme-nofiller__{ep}"
                recs = [json.loads(l) for l in (hdir / "records.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
                todo = [q for q in questions(recs, sets) if (cell, q["id"], str(q["point"])) not in done]
                if limit is not None:
                    todo = todo[: max(0, limit - n)]
                if not todo:
                    continue
                by_point = defaultdict(list)
                for q in todo:
                    by_point[str(q["point"])].append(q)
                for point, ws in replay_states(hdir, data):
                    for q in by_point.get(str(point), []):
                        res = ws.search(q["query"], k=K)
                        page_addresses = [r["address"] for r in res["results"]]
                        page = render_page(ws, res["results"])
                        msg = user_message(page, q["query"])
                        try:
                            ans = reader.answer(SYSTEM, msg)
                        except QuotaFloor as exc:
                            log(f"stopped: {exc}")
                            return results
                        parsed = parse_answer(ans.get("content"))
                        rec = {"reader": reader.name, "prompt_version": PROMPT_VERSION, "cell": cell, "episode": ep,
                               "id": q["id"], "point": q["point"], "set": q["set"], "task": q["task"], "hop": q.get("hop"),
                               "query": q["query"], "values": q.get("values"), "page": page_addresses,
                               "page_matches_record": page_addresses == [p["address"] for p in q.get("page", [])],
                               "page_chars": len(page), "answered": reader.name == "none" or ans.get("content") is not None,
                               "raw": ans.get("content"), "parsed": parsed, "valid": parsed is not None,
                               "correct": grade(q, parsed) if reader.name != "none" else None,
                               **{k: v for k, v in ans.items() if k != "content"}}
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        fh.flush()
                        results.append(rec)
                        n += 1
                        log(f"{reader.name} {cell} {q['id']}@{q['point']} {q['set']}: "
                            f"{'page ok' if rec['page_matches_record'] else 'PAGE MISMATCH'}"
                            + ("" if reader.name == "none" else f", {parsed}, correct={rec['correct']}, {rec.get('latency_s')} s"))
    return results


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        groups[(r["reader"], r["cell"], r["set"])].append(r)
    out = []
    for (reader, cell, s), rs in sorted(groups.items()):
        lat = [r["latency_s"] for r in rs if r.get("latency_s")]
        row = {"reader": reader, "cell": cell, "set": s, "n": len(rs), "valid": sum(r["valid"] for r in rs),
               "correct": sum(bool(r["correct"]) for r in rs), "pages_match": sum(r["page_matches_record"] for r in rs),
               "median_latency_s": round(statistics.median(lat), 1) if lat else None}
        for task in TASKS:
            t = [r for r in rs if r["task"] == task]
            if t:
                row[task] = f"{sum(bool(r['correct']) for r in t)}/{len(t)}"
        out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.agent.reader", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", default=os.environ.get("MINDSLICE_AGENT_RUNS") or str(Path.home() / ".cache" / "mindslice" / "agent-runs"))
    p.add_argument("--source", required=True, help="run directory holding the cells, e.g. smoke-final")
    p.add_argument("--cells", required=True, help="comma-separated cell directories, e.g. flat,oracle")
    p.add_argument("--episodes", required=True, help="comma-separated MEME episode ids, e.g. pl_001,pl_002")
    p.add_argument("--reader", required=True, help="none | qwen | a Gemini model id (gemini-4-argon-medium)")
    p.add_argument("--sets", default="target,control")
    p.add_argument("--limit", type=int, help="at most this many questions per cell")
    p.add_argument("--weekly-floor", type=float, default=0.055, help="stop Gemini calls below this weekly quota")
    p.add_argument("--data")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    reader = make_reader(args.reader, args.weekly_floor)
    recs = run(Path(args.runs) / args.source, args.cells.split(","), args.episodes.split(","), reader, Path(args.out),
               tuple(args.sets.split(",")), args.limit, args.data)
    for row in summarize(recs):
        print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
