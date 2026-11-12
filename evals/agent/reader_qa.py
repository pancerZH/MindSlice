"""Reader QA as pre-registered (PLAN.md section 11): arms, question lists, the freeze, two stages, the gate, scoring.

The lines (R1-R3) are read on ``gemini-4-argon-medium`` only. The local Qwen reads ``flat`` and ``oracle`` as a
comparison reader, with no line, to show whether the lineage effect depends on the reader. Every stage refuses to
start unless the freeze (``results/freeze_reader.json``) still matches; stage 2 refuses unless that reader passed
stage 1's gate; ``score`` refuses to print a line while a hand check is pending.

    python -m evals.agent.reader_qa freeze [--check]
    python -m evals.agent.reader_qa stage1 --reader qwen            # or gemini-4-argon-medium
    python -m evals.agent.reader_qa stage2 --reader qwen [--jobs 8]
    python -m evals.agent.reader_qa score [--write]

Answers go to ``$MINDSLICE_AGENT_RUNS/reader-qa/<reader>/`` (they hold dataset text and are never committed).
"""

from __future__ import annotations

from evals.provenance import engine_digest

import argparse
import hashlib
import json
import os
import random
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from . import reader as rd

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
FREEZE = RESULTS / "freeze_reader.json"
AUDIT = RESULTS / "audit" / "reader-qa"

LINE_READER = "gemini-4-argon-medium"
COMPARISON_READER = "qwen"
ARMS = {  # arm -> the tier-1 run directory it is read from (under $MINDSLICE_AGENT_RUNS)
    "flat": "gate1/flat",
    "oracle": "gate1/oracle",
    "argon-default": "tier1/agent-default@gemini-4-argon-medium",
    "argon-policy": "tier1/agent-policy@gemini-4-argon-medium",
    "argon-overlay": "tier1/agent-overlay@gemini-4-argon-medium",
    "flash-policy": "tier1/agent-policy@gemini-3.8-flash-medium",
    "qwen-policy": "tier1-qwen/agent-policy@qwen3.8-flash-next-iq3_s",
    "qwen-overlay": "tier1-qwen/agent-overlay@qwen3.8-flash-next-iq3_s",
}
AGENT_ARMS = tuple(a for a in ARMS if a not in ("flat", "oracle"))
ARGON_ARMS = ("argon-default", "argon-policy", "argon-overlay")
READER_ARMS = {LINE_READER: tuple(ARMS), COMPARISON_READER: ("flat", "oracle")}
VARIANCE = {LINE_READER: ("flat", "oracle")}  # their targets are read a second time
LINES = (
    {"id": "R1", "claim": "lineage over raw chunks (the mechanism)", "a": "oracle", "b": "flat", "set": "target", "line": 0.20},
    *({"id": f"R2 {a}", "claim": "agent-written memory over raw chunks", "a": a, "b": "flat", "set": "target", "line": 0.10}
      for a in ARGON_ARMS),
    *({"id": f"R3 {a}", "claim": "no harm before the change", "a": a, "b": "flat", "set": "control", "line": -0.05}
      for a in ("oracle", *AGENT_ARMS)),
)
GATE = {"max_invalid": 0.05, "min_control_accuracy": 0.80, "repeats": 40, "min_repeat_agreement": 36}
SEED = 20261106
TRANSPORT_RETRIES = (10, 60, 300)  # seconds before each retry of a failed call (not an invalid answer)


def runs_root() -> Path:
    return Path(os.environ.get("MINDSLICE_AGENT_RUNS") or Path.home() / ".cache" / "mindslice" / "agent-runs")


def _digest(files) -> str:
    h = hashlib.sha256()
    for f in files:
        h.update(Path(f).name.encode() + b"\0" + Path(f).read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


def episodes(root: Path) -> list[str]:
    return sorted(p.name for p in (root / ARMS["flat"]).iterdir() if p.name.startswith("meme-nofiller__"))


def unit(q: dict[str, Any]) -> str:
    return f"{q['episode']}|{q['id']}|{q['point']}"


def arm_questions(root: Path, arm: str, sets=("target", "control")) -> list[dict[str, Any]]:
    out = []
    for ep in episodes(root):
        recs = [json.loads(l) for l in (root / ARMS[arm] / ep / "records.jsonl").read_text(encoding="utf-8").splitlines()
                if l.strip()]
        out += [{**q, "arm": arm, "episode": ep} for q in rd.questions(recs, sets)]
    return out


def repeat_units(root: Path) -> list[tuple[str, str]]:
    """The 40 control questions of ``flat`` and ``oracle`` asked twice in stage 1 (fixed by the seed)."""
    pool = sorted((arm, unit(q)) for arm in ("flat", "oracle") for q in arm_questions(root, arm, ("control",)))
    return sorted(random.Random(SEED).sample(pool, GATE["repeats"]))


# ---------------------------------------------------------------------------
# The freeze
# ---------------------------------------------------------------------------


def facts(root: Path) -> dict[str, Any]:
    eps = episodes(root)
    counts, listing, inputs = {}, [], []
    for arm, src in ARMS.items():
        if sorted(p.name for p in (root / src).iterdir() if p.name.startswith("meme-nofiller__")) != eps:
            raise SystemExit(f"{arm}: its episodes differ from flat's")
        qs = arm_questions(root, arm)
        counts[arm] = {s: sum(q["set"] == s for q in qs) for s in ("target", "control")}
        listing += [[arm, unit(q), q["set"], q["task"]] for q in qs]
        for ep in eps:
            inputs += [f for f in (root / src / ep / "records.jsonl", root / src / ep / "calls.jsonl") if f.exists()]
    package = HERE.parent.parent / "mindslice"
    return {
        "plan": "PLAN.md section 11",
        "harness_digest": _digest([HERE / "reader.py", HERE / "reader_qa.py"]),
        "engine_digest": engine_digest(package),
        "prompt_version": rd.PROMPT_VERSION,
        "system_prompt_sha256": hashlib.sha256(rd.SYSTEM.encode()).hexdigest(),
        "line_reader": LINE_READER,
        "comparison_reader": COMPARISON_READER,
        "reader_arms": {k: list(v) for k, v in READER_ARMS.items()},
        "variance": {k: list(v) for k, v in VARIANCE.items()},
        "arms": ARMS,
        "episodes": eps,
        "questions": counts,
        "questions_sha256": hashlib.sha256(json.dumps(listing).encode()).hexdigest(),
        "inputs_sha256": _digest(inputs),
        "repeat_units": [list(u) for u in repeat_units(root)],
        "lines": list(LINES),
        "gate": GATE,
        "bootstrap": {"replicates": 2000, "seed": SEED},
        "readers": {LINE_READER: {"via": "agy", "effort": "medium", "agent": rd.GeminiReader.AGENT},
                    COMPARISON_READER: {"model": rd.QwenReader().model, "temperature": 0, "seed": SEED,
                                        "cache_prompt": False, "max_tokens": rd.QwenReader().max_tokens}},
    }


def check(root: Path) -> list[str]:
    if not FREEZE.exists():
        return [f"{FREEZE} is missing: run `python -m evals.agent.reader_qa freeze` and commit PLAN.md first"]
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    now = facts(root)
    return [f"{k} changed since the freeze" for k in now if frozen.get(k) != now[k]]


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


class Retrying:
    """A reader whose failed calls (transport errors, a failed CLI run) are retried; invalid answers are not."""

    def __init__(self, inner, gate=None, sleep=time.sleep) -> None:
        self.inner, self.name, self.gate, self.sleep = inner, inner.name, gate, sleep

    def answer(self, system: str, user: str) -> dict[str, Any]:
        last: Exception | None = None
        for wait in (*TRANSPORT_RETRIES, None):
            try:
                ans = self.inner.answer(system, user)
            except rd.QuotaFloor:
                raise
            except Exception as exc:  # noqa: BLE001 - network or server failure
                last = exc
            else:
                failed = ans.get("exit_code") not in (None, 0) or ans.get("status") not in (None, "SUCCESS")
                if not failed:
                    return ans
                last = RuntimeError(f"reader call failed: exit {ans.get('exit_code')}, status {ans.get('status')}")
                if self.gate is not None:
                    self.gate.wait(force=True)  # a quota failure waits for the reset
            if wait is None:
                break
            self.sleep(wait)
        raise RuntimeError(f"{self.name}: gave up after {len(TRANSPORT_RETRIES) + 1} attempts: {last}")


def make(reader_name: str):
    if reader_name == LINE_READER:
        from . import agy

        gate = agy.QuotaGate()
        return Retrying(rd.GeminiReader(LINE_READER, gate=gate), gate=gate)
    if reader_name == COMPARISON_READER:
        return Retrying(rd.QwenReader())
    raise SystemExit(f"{reader_name} is not a reader of this run (line: {LINE_READER}; comparison: {COMPARISON_READER})")


def out_dir(root: Path, reader_name: str) -> Path:
    return root / "reader-qa" / reader_name


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def stage_items(root: Path, reader_name: str, stage: int) -> dict[str, list[dict[str, Any]]]:
    """File name -> the questions it must hold, for one reader and stage."""
    if stage == 1:
        controls = [q for arm in ("flat", "oracle") for q in arm_questions(root, arm, ("control",))]
        rep = set(map(tuple, repeat_units(root)))
        return {"stage1.jsonl": controls, "repeats.jsonl": [q for q in controls if (q["arm"], unit(q)) in rep]}
    arms = READER_ARMS[reader_name]
    items = [q for arm in arms for q in arm_questions(root, arm, ("target",))]
    items += [q for arm in arms if arm in AGENT_ARMS for q in arm_questions(root, arm, ("control",))]
    out = {"stage2.jsonl": items}
    if reader_name in VARIANCE:
        out["variance.jsonl"] = [q for arm in VARIANCE[reader_name] for q in arm_questions(root, arm, ("target",))]
    return out


def run_file(root: Path, reader, path: Path, items: list[dict[str, Any]], jobs: int, log=print) -> int:
    done = {(r["arm"], r["unit"]) for r in _load(path) if r.get("answered")}
    todo = [q for q in items if (q["arm"], unit(q)) not in done]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for q in todo:
        groups[(q["arm"], q["episode"])].append(q)
    lock = threading.Lock()
    path.parent.mkdir(parents=True, exist_ok=True)
    n = [0]

    def work(arm: str, ep: str, qs: list[dict[str, Any]]) -> None:
        for rec in rd.ask_haystack(reader, root / ARMS[arm] / ep, qs):
            q = next(x for x in qs if x["id"] == rec["id"] and str(x["point"]) == str(rec["point"]))
            rec = {"arm": arm, "episode": ep, "unit": unit(q), **rec}
            with lock, open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n[0] += 1
                if n[0] % 25 == 0:
                    log(f"{path.name}: {len(done) + n[0]}/{len(items)}")

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = [pool.submit(work, arm, ep, qs) for (arm, ep), qs in sorted(groups.items())]
        for f in as_completed(futures):
            f.result()
    return n[0]


def gate_result(root: Path, reader_name: str) -> dict[str, Any]:
    d = out_dir(root, reader_name)
    s1, rep = _load(d / "stage1.jsonl"), _load(d / "repeats.jsonl")
    allrecs = s1 + rep
    invalid = sum(not r["valid"] for r in allrecs) / len(allrecs) if allrecs else 1.0
    acc = {}
    for arm in ("flat", "oracle"):
        rs = [r for r in s1 if r["arm"] == arm]
        acc[arm] = sum(bool(r["correct"]) for r in rs) / len(rs) if rs else 0.0
    first = {(r["arm"], r["unit"]): (r.get("parsed") or {}).get("status") for r in s1}
    agree = sum(first.get((r["arm"], r["unit"])) == (r.get("parsed") or {}).get("status") for r in rep)
    complete = len(s1) == len(stage_items(root, reader_name, 1)["stage1.jsonl"]) and len(rep) == GATE["repeats"]
    ok = (complete and invalid <= GATE["max_invalid"] and min(acc.values()) >= GATE["min_control_accuracy"]
          and agree >= GATE["min_repeat_agreement"])
    return {"reader": reader_name, "complete": complete, "pass": ok, "invalid_share": round(invalid, 4),
            "control_accuracy": {k: round(v, 4) for k, v in acc.items()}, "repeat_agreement": f"{agree}/{len(rep)}",
            "gate": GATE}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def handcheck_cases(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``current`` answers the value rule rejected, where a value is graded (controls, Cascade targets)."""
    out = []
    for r in records:
        p = r.get("parsed") or {}
        if p.get("status") == "current" and not r["correct"] and (r["set"] == "control" or r["task"] == "Cas"):
            out.append({"arm": r["arm"], "unit": r["unit"], "set": r["set"], "task": r["task"], "query": r["query"],
                        "answer": p.get("value"), "gold": (r.get("values") or {}).get("current"), "verdict": None})
    return sorted(out, key=lambda c: (c["arm"], c["unit"]))


def correctness(records: list[dict[str, Any]], verdicts: dict[tuple[str, str], bool]) -> dict[tuple[str, str], dict[str, float]]:
    """(arm, set) -> unit -> 1.0/0.0, with hand verdicts applied."""
    out: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for r in records:
        ok = verdicts.get((r["arm"], r["unit"]), bool(r["correct"]))
        out[(r["arm"], r["set"])][r["unit"]] = 1.0 if ok else 0.0
    return out


def paired(c: dict, a: str, b: str, set_: str) -> dict[str, float]:
    from evals.external.score import paired_ci

    ua, ub = c.get((a, set_), {}), c.get((b, set_), {})
    keys = sorted(set(ua) & set(ub))
    out = paired_ci([ua[k] for k in keys], [ub[k] for k in keys])
    out["unpaired"] = len(set(ua) ^ set(ub))
    return out


def score(root: Path) -> dict[str, Any]:
    from evals.external.score import mean_ci, verdict_of

    result: dict[str, Any] = {"readers": {}}
    per_reader: dict[str, dict] = {}
    for reader_name in (LINE_READER, COMPARISON_READER):
        d = out_dir(root, reader_name)
        recs = _load(d / "stage1.jsonl") + _load(d / "stage2.jsonl")
        if not recs:
            continue
        sheet = AUDIT / f"{reader_name}.json"
        cases = handcheck_cases(recs)
        if sheet.exists():
            judged = {(c["arm"], c["unit"]): c for c in json.loads(sheet.read_text(encoding="utf-8"))["cases"]}
            cases = [judged.get((c["arm"], c["unit"]), c) for c in cases]
        pending = [c for c in cases if c["verdict"] is None]
        verdicts = {(c["arm"], c["unit"]): c["verdict"] == "correct" for c in cases if c["verdict"] is not None}
        c = correctness(recs, verdicts)
        if not pending:
            per_reader[reader_name] = c
        rr: dict[str, Any] = {"records": len(recs), "handcheck": {"cases": len(cases), "pending": len(pending)},
                              "accuracy": {f"{a} {s}": mean_ci([u[k] for k in sorted(u)]) for (a, s), u in sorted(c.items())}}
        by_task = defaultdict(lambda: [0, 0])
        for r in recs:
            key = f"{r['arm']} {r['set']} {r['task']}" + (f" hop {r['hop']}" if r.get("hop") else "")
            by_task[key][0] += verdicts.get((r["arm"], r["unit"]), bool(r["correct"]))
            by_task[key][1] += 1
        rr["by_task"] = {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_task.items())}
        if pending:
            rr["lines"] = f"withheld: {len(pending)} hand checks pending in {sheet}"
        elif reader_name == LINE_READER:
            rr["lines"] = [{**line, **(st := paired(c, line["a"], line["b"], line["set"])),
                            "verdict": verdict_of(st, line["line"])} for line in LINES]
        else:
            rr["comparison"] = {s: paired(c, "oracle", "flat", s) for s in ("target", "control")}
        var = _load(d / "variance.jsonl")
        if var:
            first = {(r["arm"], r["unit"]): bool(r["correct"]) for r in recs if r["set"] == "target"}
            same = sum(first.get((r["arm"], r["unit"])) == bool(r["correct"]) for r in var)
            rr["variance"] = {"repeated": len(var), "same_correctness": same,
                              "second_run_accuracy": {a: round(sum(bool(r["correct"]) for r in var if r["arm"] == a)
                                                               / max(1, sum(r["arm"] == a for r in var)), 4)
                                                      for a in VARIANCE.get(reader_name, ())}}
        result["readers"][reader_name] = rr
        if not sheet.exists() and cases:
            sheet.parent.mkdir(parents=True, exist_ok=True)
            sheet.write_text(json.dumps({"reader": reader_name, "cases": cases}, indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    if LINE_READER in per_reader and COMPARISON_READER in per_reader:
        result["reader_dependence"] = reader_dependence(per_reader[LINE_READER], per_reader[COMPARISON_READER])
    return result


def reader_dependence(a: dict, q: dict) -> dict[str, Any]:
    """Per unit both readers read in both arms: (Argon oracle - Argon flat) - (Qwen oracle - Qwen flat).

    Near 0: the lineage effect doesn't depend on which of the two reads. Reported, no line."""
    from evals.external.score import mean_ci

    out = {}
    for s in ("target", "control"):
        maps = [a.get(("oracle", s), {}), a.get(("flat", s), {}), q.get(("oracle", s), {}), q.get(("flat", s), {})]
        keys = sorted(set.intersection(*(set(m) for m in maps))) if all(maps) else []
        out[s] = mean_ci([(maps[0][k] - maps[1][k]) - (maps[2][k] - maps[3][k]) for k in keys])
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.agent.reader_qa", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--check", action="store_true")
    for name in ("stage1", "stage2"):
        s = sub.add_parser(name)
        s.add_argument("--reader", required=True)
        s.add_argument("--jobs", type=int, default=1)
    sc = sub.add_parser("score")
    sc.add_argument("--write", action="store_true")
    args = p.parse_args(argv)
    root = runs_root()
    if args.command == "freeze":
        if args.check:
            diffs = check(root)
            print("\n".join(diffs) if diffs else "the freeze matches")
            return 1 if diffs else 0
        if FREEZE.exists():
            raise SystemExit(f"{FREEZE} exists; the freeze is written once")
        FREEZE.write_text(json.dumps({"frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **facts(root)},
                                     indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {FREEZE}")
        return 0
    if args.command in ("stage1", "stage2"):
        diffs = check(root)
        if diffs:
            raise SystemExit("refusing to run: " + "; ".join(diffs))
        stage = int(args.command[-1])
        if stage == 2 and not gate_result(root, args.reader)["pass"]:
            raise SystemExit(f"refusing to run stage 2: {args.reader} has not passed stage 1 ({gate_result(root, args.reader)})")
        reader = make(args.reader)
        d = out_dir(root, args.reader)
        for name, items in stage_items(root, args.reader, stage).items():
            run_file(root, reader, d / name, items, args.jobs)
        if stage == 1:
            g = gate_result(root, args.reader)
            (d / "gate.json").write_text(json.dumps(g, indent=1) + "\n", encoding="utf-8")
            print(json.dumps(g))
        return 0
    res = score(root)
    text = json.dumps(res, indent=1, ensure_ascii=False)
    print(text)
    if args.write:
        (RESULTS / "reader_qa.json").write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
