"""Agent-in-the-loop lineage test (``evals/agent_test.md``): runner, scorer and reports.

    python -m evals.agent offline --tier 1 --run gate1              # flat, oracle and the scripted agents
    python -m evals.agent gate --run gate1                         # Gate 1: scripted agents vs flat / oracle
    python -m evals.agent agy --tier smoke --run smoke --arms agent-default --models gemini-3.8-flash-medium
    python -m evals.agent report --run smoke [--write NAME]        # metrics, lines and telemetry of a run
    python -m evals.agent prompts                                   # the prompts' SHA-256 digests

Runs live outside the repository (``$MINDSLICE_AGENT_RUNS``, default ``~/.cache/mindslice/agent-runs``):
one directory per arm, model and haystack, holding the workspace (``ws/overlay`` kept for auditing),
``records.jsonl`` (every judgment), ``calls.jsonl`` (every tool call) and, for LLM arms, the agent traces.
They hold dataset text and are never committed; ``results/`` gets the generated summaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import mindslice
from evals.external import sources

from . import score
from .prompts import digests
from .runner import run_haystack
from .sessions import tier_haystacks

HERE = Path(__file__).parent
RESULTS = HERE / "results"
RUNS_ENV = "MINDSLICE_AGENT_RUNS"
OFFLINE_ARMS = ("flat", "oracle", "scripted-flat", "scripted-oracle", "scripted-overlay")
LLM_ARMS = ("agent-default", "agent-policy", "agent-overlay")
MODELS = ("gemini-3.8-flash-medium", "gemini-4-argon-medium")
MAIN_MODEL = "gemini-4-argon-medium"  # the more capable of the two: the variance repeats use it (8.4)
FLASH = "gemini-3.8-flash-medium"
# Tier 1's matrix (PLAN.md, re-frozen before any tier-1 call): every arm on the main model, and agent-policy
# on Flash. Flash agent-default and agent-overlay were left out on the smoke tier's cost and cap evidence.
MATRIX = (("agent-default", MAIN_MODEL), ("agent-policy", MAIN_MODEL), ("agent-overlay", MAIN_MODEL), ("agent-policy", FLASH))
EXCLUDED = (("agent-default", FLASH), ("agent-overlay", FLASH))
# Dropped from tier 1 after its first 329 sessions, before any tier-1 record was read (PLAN.md ledger): the
# 231-batch MemoryAgentBench chain alone needed about a quarter of the week's quota. The tier itself is unchanged.
TIER1_DROPPED = ("mab-sh/factconsolidation_sh_32k",)
SCORER_FILES = ("judge.py", "plan.py", "score.py", "sessions.py")


def runs_root(override: str | None = None) -> Path:
    return Path(override or os.environ.get(RUNS_ENV) or Path.home() / ".cache" / "mindslice" / "agent-runs").expanduser()


def slug(key: str) -> str:
    return key.replace("/", "__")


def arm_dir(run: Path, arm: str, model: str | None = None) -> Path:
    return run / (f"{arm}@{model}" if model else arm)


# ---------------------------------------------------------------------------
# Offline arms
# ---------------------------------------------------------------------------


def _offline_job(args: tuple[str, str, str, str | None]) -> tuple[str, str, float]:
    arm, key, out, data = args
    from evals.external.datasets import LOADERS

    dataset = key.split("/", 1)[0]
    h = next(x for x in LOADERS[dataset](Path(data) if data else None) if x.key == key)
    t0 = time.time()
    run_haystack(h, arm, Path(out))
    return arm, key, time.time() - t0


def offline(tier: str, arms: list[str], run: Path, jobs: int, data: Path | None, log=print) -> None:
    keys = [h.key for h in tier_haystacks(tier, data)]
    work = [(arm, k, str(arm_dir(run, arm) / slug(k)), str(data) if data else None) for arm in arms for k in keys]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        futs = [pool.submit(_offline_job, w) for w in work]
        for i, f in enumerate(as_completed(futs), 1):
            arm, key, dt = f.result()
            if i % 25 == 0 or i == len(work):
                log(f"{i}/{len(work)} done ({time.time() - t0:.0f}s); last {arm} {key} {dt:.1f}s")
    (run / "run.json").write_text(json.dumps({"tier": tier, "environment": environment(), "arms": arms}, indent=1) + "\n")


# ---------------------------------------------------------------------------
# Loading and summarizing
# ---------------------------------------------------------------------------


def load_arm(path: Path) -> list[dict[str, Any]]:
    out = []
    for d in sorted(p for p in path.iterdir() if p.is_dir()):
        f = d / "records.jsonl"
        if f.exists():
            with open(f, encoding="utf-8") as fh:
                out += [json.loads(l) for l in fh if l.strip()]
    return out


def load_run(run: Path) -> dict[str, list[dict[str, Any]]]:
    return {p.name: load_arm(p) for p in sorted(run.iterdir()) if p.is_dir()}


def summarize(arms: dict[str, list[dict[str, Any]]], flat_arm: str = "flat") -> dict[str, Any]:
    us = {a: score.units(r) for a, r in arms.items()}
    out: dict[str, Any] = {"arms": {}}
    for a, recs in arms.items():
        out["arms"][a] = {"pooled": score.pooled(us[a]), "groups": score.groups_table(us[a]),
                          "telemetry": score.telemetry(recs)}
        if flat_arm in us and a != flat_arm and a.startswith("agent-"):
            out["arms"][a]["lines"] = score.lines(us[a], us[flat_arm])
    out["comparisons"] = comparisons(us)
    return out


COMPARISONS = (
    ("agent-policy minus agent-default (Argon)", f"agent-policy@{MAIN_MODEL}", f"agent-default@{MAIN_MODEL}"),
    ("agent-overlay minus agent-policy (Argon)", f"agent-overlay@{MAIN_MODEL}", f"agent-policy@{MAIN_MODEL}"),
    ("Argon minus Flash (agent-policy)", f"agent-policy@{MAIN_MODEL}", f"agent-policy@{FLASH}"),
)


def comparisons(us: dict[str, dict[str, dict[str, float]]]) -> dict[str, Any]:
    """The plan's paired differences between cells, per pooled metric (paired by unit)."""
    out = {}
    for name, a, b in COMPARISONS:
        if a in us and b in us:
            out[name] = {m: score.paired(us[a], us[b], m, gs) for m, gs in score.POOLED.items()}
    return out


def variance(main: list[dict[str, Any]], repeats: list[list[dict[str, Any]]], episodes: list[str]) -> dict[str, Any]:
    """Run-to-run spread of agent-policy on the main model over the fixed episodes: each pooled metric in the
    tier-1 run and each repeat, restricted to those episodes."""
    keep = set(episodes)
    runs = [main] + repeats
    per = []
    for recs in runs:
        u = score.units([r for r in recs if r["haystack"] in keep])
        per.append({m: score.stat(u, m, gs) for m, gs in score.POOLED.items()})
    out: dict[str, Any] = {"runs": len(runs), "episodes": len(keep), "metrics": {}}
    for m in score.POOLED:
        xs = [p[m]["mean"] for p in per if p[m]["n"]]
        if not xs:
            continue
        mu = sum(xs) / len(xs)
        sd = (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5 if len(xs) > 1 else 0.0
        out["metrics"][m] = {"per_run": [round(x, 4) for x in xs], "mean": round(mu, 4), "sd": round(sd, 4),
                             "min": round(min(xs), 4), "max": round(max(xs), 4), "n_per_run": per[0][m]["n"]}
    return out


def audit_corrected(records: list[dict[str, Any]], verdicts: dict[str, Any]) -> dict[str, Any]:
    """``retired`` and ``lost`` with the audit's matching errors taken out (6.3; not a pre-registered line).

    Failures (``retired``) and losses (``lost``) the audit judged matching errors are counted as passes.
    When the audit judged every case the correction is exact; when it judged a sample, the sample's share
    of matching errors is applied to the whole population."""
    out: dict[str, Any] = {}
    for kind, metric, key in (("retired", "retired", "update"), ("lost", "lost", "value")):
        units = [r for r in records if r["kind"] == key and r.get("matchable")]
        n = len(units)
        bad = sum(1 for r in units if r.get(metric) is (kind == "lost")) if kind == "lost" else \
            sum(1 for r in units if r.get("retired") is False)
        rows = verdicts["cases"].get(kind, [])
        judged = [r for r in rows if r.get("verdict")]
        errors = sum(1 for r in judged if r["verdict"] == "matching error")
        share = errors / len(judged) if judged else 0.0
        exact = len(judged) == bad
        true_bad = (bad - errors) if exact else bad * (1 - share)
        raw = (1 - bad / n) if kind == "retired" else bad / n
        fixed = (1 - true_bad / n) if kind == "retired" else true_bad / n
        out[metric] = {"n": n, "flagged": bad, "audited": len(judged), "matching_errors": errors,
                       "share": round(share, 3), "raw": round(raw, 4), "corrected": round(fixed, 4), "exact": exact}
    return out


def gate(arms: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Gate 1 (agent_test.md 7.4): each scripted agent against the arm it must reproduce, unit by unit."""
    us = {a: score.units(r) for a, r in arms.items()}
    out = {}
    for scripted, ref in (("scripted-flat", "flat"), ("scripted-oracle", "oracle"), ("scripted-overlay", "oracle")):
        if scripted not in us or ref not in us:
            continue
        a, b = us[scripted], us[ref]
        metrics = sorted({m for v in a.values() for m in v if not m.startswith("_")})
        rows = {}
        for m in metrics:
            keys = sorted(k for k in set(a) & set(b) if m in a[k] and m in b[k])
            diff = [k for k in keys if a[k][m] != b[k][m]]
            rows[m] = {"units": len(keys), "disagree": len(diff), "examples": diff[:6],
                       "scripted": score.stat(a, m, score.POOLED.get(m)), "reference": score.stat(b, m, score.POOLED.get(m)),
                       "paired": score.paired(a, b, m, score.POOLED.get(m)),
                       "only_one_side": len({k for k in a if m in a[k]} ^ {k for k in b if m in b[k]})}
        out[f"{scripted} vs {ref}"] = rows
    return out


def compare_levels(arms: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Value-based vs card-level (``evals.external.score.state``) on the same first pages (flat and oracle)."""
    out: dict[str, Any] = {}
    for arm in ("flat", "oracle"):
        recs = [r for r in arms.get(arm, []) if r["kind"] == "question" and r.get("card")]
        by: dict[str, dict[str, dict[str, list]]] = {}
        for r in recs:
            g = score.group(r)
            v, c = score.question_metrics(r), score.card_metrics(r)
            for m in ("stale-first", "stale@10", "current@10", "history-named@10"):
                if m in v or m in c:
                    e = by.setdefault(g, {}).setdefault(m, {"value": [], "card": [], "both": [], "ids": []})
                    if m in v:
                        e["value"].append(v[m])
                    if m in c:
                        e["card"].append(c[m])
                    if m in v and m in c:
                        e["both"].append((v[m], c[m]))
                        if v[m] != c[m]:
                            e["ids"].append(r["id"])
        out[arm] = {g: {m: {"value": score.mean_ci(e["value"]), "card": score.mean_ci(e["card"]),
                            "disagree": len(e["ids"]), "paired_n": len(e["both"]), "examples": e["ids"][:4]}
                        for m, e in ms.items()} for g, ms in sorted(by.items())}
    return out


def retrace(run: Path) -> dict[str, int]:
    """Recompute each LLM session's trace check (``agy.trace_check``) from its saved trace and proxy log and
    update the two telemetry fields in ``records.jsonl`` (used after the check itself was corrected)."""
    from . import agy

    out = {"sessions": 0, "mismatches": 0}
    for h in sorted(run.glob("agent-*/*")):
        f = h / "records.jsonl"
        if not f.exists():
            continue
        rows = [json.loads(l) for l in (h / "calls.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        recs = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        for r in recs:
            if r["kind"] != "session" or not r.get("attempts"):
                continue
            a = len(r["attempts"]) - 1
            st = h / "agy" / f"s{r['session']:03d}" / f"stream{a}.jsonl"
            mine = [x for x in rows if x.get("kind") == "tools/call" and x["session"] == r["session"] and x.get("attempt") == a]
            chk = agy.trace_check(agy.tool_calls(agy.read_stream(st)), mine)
            r["trace_matches_proxy"], r["client_rejected_calls"] = chk["ok"], chk["client_rejected"]
            out["sessions"] += 1
            out["mismatches"] += not chk["ok"]
        f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    return out


def projection(arms: dict[str, list[dict[str, Any]]], tier: str = "1", data: Path | None = None,
               concurrency: tuple[int, ...] = (8, 16)) -> dict[str, Any]:
    """Tier cost from a smoke run (8.2): per arm and model, mean wall time and tokens per MEME session and
    per MemoryAgentBench batch, scaled to the tier's sessions; wall clock at a given concurrency is bounded
    below by the longest haystack (its sessions run in order)."""
    from .sessions import agent_sessions

    hs = tier_haystacks(tier, data)
    n_meme = sum(len(agent_sessions(h)) for h in hs if h.dataset != "mab-sh")
    n_mab = sum(len(agent_sessions(h)) for h in hs if h.dataset == "mab-sh")
    longest_mab = max((len(agent_sessions(h)) for h in hs if h.dataset == "mab-sh"), default=0)
    reading = {(h.key, s.index): len(s.transcript) / 4 for h in tier_haystacks("smoke", data) for s in agent_sessions(h)}
    out: dict[str, Any] = {"tier": tier, "sessions": {"meme": n_meme, "mab": n_mab}, "per_arm": {}}
    total_s = 0.0
    for arm, recs in arms.items():
        sess = [r for r in recs if r["kind"] == "session" and r.get("usage")]
        if not sess or not arm.startswith("agent-"):
            continue
        def mean(xs):
            xs = list(xs)
            return sum(xs) / len(xs) if xs else 0.0
        meme = [r for r in sess if r["dataset"] != "mab-sh"]
        mab = [r for r in sess if r["dataset"] == "mab-sh"]
        # Context the model read: uncached input plus cache reads (the CLI reports them apart, per step).
        ctx = lambda r: (r["usage"].get("input_tokens") or 0) + (r["usage"].get("cache_read_tokens") or 0)
        tok = lambda rs, k: mean((ctx(r) if k == "input_tokens" else (r["usage"].get(k) or 0)) for r in rs)
        est = {"wall_s_meme": round(mean(r["wall_s"] for r in meme), 1), "wall_s_mab": round(mean(r["wall_s"] for r in mab), 1),
               "input_tokens_meme": round(tok(meme, "input_tokens")), "input_tokens_mab": round(tok(mab, "input_tokens")),
               "output_tokens_meme": round(tok(meme, "output_tokens")), "output_tokens_mab": round(tok(mab, "output_tokens")),
               "smoke_sessions": len(sess), "smoke_input_tokens": sum(ctx(r) for r in sess)}
        read = sum(reading.get((r["haystack"], r["session"]), 0) for r in sess)
        est["token_multiple"] = round(est["smoke_input_tokens"] / read, 1) if read else None  # input tokens per token read
        est["tier_session_hours"] = round((n_meme * est["wall_s_meme"] + n_mab * est["wall_s_mab"]) / 3600, 1)
        est["tier_input_tokens_M"] = round((n_meme * est["input_tokens_meme"] + n_mab * est["input_tokens_mab"]) / 1e6, 1)
        est["tier_output_tokens_M"] = round((n_meme * est["output_tokens_meme"] + n_mab * est["output_tokens_mab"]) / 1e6, 2)
        est["longest_haystack_hours"] = round(longest_mab * est["wall_s_mab"] / 3600, 1)
        total_s += n_meme * est["wall_s_meme"] + n_mab * est["wall_s_mab"]
        out["per_arm"][arm] = est
    crit = max((e["longest_haystack_hours"] for e in out["per_arm"].values()), default=0.0)
    out["all_arms_session_hours"] = round(total_s / 3600, 1)
    out["wall_clock_hours"] = {c: round(max(total_s / 3600 / c, crit), 1) for c in concurrency}
    return out


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def _digest(files) -> str:
    return hashlib.sha256(b"".join(f.name.encode() + b"\0" + f.read_bytes() for f in files)).hexdigest()


RUNNER_FILES = ("agents.py", "agy.py", "judge.py", "mcp_proxy.py", "plan.py", "prompts.py", "runner.py", "score.py",
                "sessions.py", "tool_gate.py", "tools.py")  # all that runs a session or scores one (not CLI or rendering)
FREEZE = RESULTS / "freeze.json"
VARIANCE_EPISODES, VARIANCE_REPEATS, AUDIT_SEED = 20, 3, 20261106


def runner_digest() -> str:
    return _digest([HERE / f for f in RUNNER_FILES] + [HERE.parent / "external" / "datasets.py",
                                                         HERE.parent / "external" / "corpus.py", HERE.parent / "external" / "harness.py"])


def variance_episodes(data: Path | None) -> list[str]:
    import random

    keys = sorted(h.key for h in tier_haystacks("1", data) if h.dataset == "meme-nofiller")
    return sorted(random.Random(AUDIT_SEED).sample(keys, VARIANCE_EPISODES))


def frozen_facts(data: Path | None) -> dict[str, Any]:
    """Everything PLAN.md freezes that can be checked mechanically before a tier-1 run."""
    from . import agy
    from .score import LINES
    from .tools import CAP

    env = environment()
    return {"engine_commit": env["commit"], "engine_digest": env["engine_digest"], "engine_dirty": env["engine_dirty"],
            "scorer_digest": env["scorer_digest"], "runner_digest": runner_digest(), "prompts": digests(),
            "agy_version": agy.agy_version(), "agy_flags": list(agy.FLAGS), "effort": "medium", "models": list(MODELS),
            "main_model": MAIN_MODEL, "agent_frontmatter": agy.FRONTMATTER, "eager_tools": list(agy.MCP_TOOLS),
            "tool_gate": "PreToolUse: allow mcp_* only", "cap": CAP, "session_timeout_s": agy.TIMEOUT_S,
            "retries": agy.RETRIES, "arms": list(LLM_ARMS),
            "matrix": [list(c) for c in MATRIX], "excluded": [list(c) for c in EXCLUDED],
            "schedule": "tier 1: main-model cells, then agent-policy on Flash, then the variance repeats",
            "tier1_dropped": list(TIER1_DROPPED),
            "quota_gate": {"min_5h": agy.QUOTA_MIN_5H, "min_weekly": agy.QUOTA_MIN_WEEKLY, "group": agy.QUOTA_GROUP},
            "tiers": {t: [h.key for h in tier_haystacks(t, data)] for t in ("smoke", "1")},
            "variance": {"arm": "agent-policy", "model": MAIN_MODEL, "repeats": VARIANCE_REPEATS,
                         "episodes": variance_episodes(data)},
            "audit": {"seed": AUDIT_SEED, "retired_failures": 50, "lost_cases": 50, "unreliable_above": 0.20},
            "lines": [{k: l[k] for k in ("id", "stat", "line")} for l in LINES]}


def check_freeze(data: Path | None) -> list[str]:
    """Differences between the frozen facts and the current ones (empty: safe to run tier 1)."""
    if not FREEZE.exists():
        return [f"{FREEZE} is missing: run `python -m evals.agent freeze` and commit PLAN.md first"]
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    now = frozen_facts(data)
    keys = ("engine_digest", "scorer_digest", "runner_digest", "prompts", "agy_version", "agy_flags", "agent_frontmatter",
            "cap", "tiers", "variance", "lines", "matrix", "quota_gate", "tier1_dropped")
    out = [f"{k} changed since the freeze" for k in keys if frozen.get(k) != now.get(k)]
    if now["engine_dirty"]:
        out.append("mindslice/ has uncommitted changes")
    return out


def _deferred(d: Path) -> bool:
    """A variance item marked deferred (its records.jsonl holds only a {"kind": "deferred"} line)."""
    f = d / "records.jsonl"
    if not f.exists():
        return False
    try:
        lines = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    except json.JSONDecodeError:
        return False
    return len(lines) == 1 and lines[0].get("kind") == "deferred"


def tier1_work(root: Path, data: Path | None) -> list[tuple[Path, str, str, Any]]:
    """The tier-1 schedule as run: the main model's three cells (MEME haystacks round-robin across arms), then
    agent-policy on Flash, then the variance repeats (PLAN.md ledger); the dropped haystacks left out."""
    hs = [h for h in tier_haystacks("1", data) if h.key not in TIER1_DROPPED]
    by_key = {h.key: h for h in hs}
    main = [c for c in MATRIX if c[1] == MAIN_MODEL]
    rest = [c for c in MATRIX if c[1] != MAIN_MODEL]
    run = root / "tier1"
    work = [(run, a, m, h) for h in hs for a, m in main]
    for a, m in rest:
        work += [(run, a, m, h) for h in hs]
    for r in range(1, VARIANCE_REPEATS + 1):
        work += [(root / f"tier1-var{r}", "agent-policy", MAIN_MODEL, by_key[k]) for k in variance_episodes(data)]
    return work


def scorer_digest() -> str:
    """judge, plan, score and sessions, plus the value export they rely on (evals/external/datasets.py)."""
    files = [HERE / f for f in SCORER_FILES] + [HERE.parent / "external" / "datasets.py"]
    return _digest(files)


def environment() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=HERE).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    package = Path(mindslice.__file__).parent
    return {"mindslice": mindslice.__version__, "commit": git("rev-parse", "--short", "HEAD"),
            "engine_dirty": bool(git("status", "--porcelain", "--", str(package))),
            "engine_digest": _digest(sorted(package.glob("*.py"))), "scorer_digest": scorer_digest(),
            "runner_digest": runner_digest(), "prompts": digests(), "python": sys.version.split()[0]}


def main(argv: list[str] | None = None) -> int:
    from .report import render_gate, render_run

    p = argparse.ArgumentParser(prog="python -m evals.agent", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", help=f"dataset directory (default ${sources.DATA_ENV})")
    p.add_argument("--runs", help=f"runs directory (default ${RUNS_ENV} or ~/.cache/mindslice/agent-runs)")
    sub = p.add_subparsers(dest="command", required=True)
    o = sub.add_parser("offline", help="run flat, oracle and the scripted agents")
    o.add_argument("--tier", default="1")
    o.add_argument("--arms", default=",".join(OFFLINE_ARMS))
    o.add_argument("--run", required=True)
    o.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    g = sub.add_parser("gate", help="Gate 1: scripted agents against flat and oracle")
    g.add_argument("--run", required=True)
    g.add_argument("--write", action="store_true")
    r = sub.add_parser("report", help="metrics, lines and telemetry of a run")
    r.add_argument("--run", required=True)
    r.add_argument("--flat-from", help="another run whose flat arm pairs with this one (G1, G3)")
    r.add_argument("--write", help="also write results/<NAME>.md and .json")
    r.add_argument("--no-lines", action="store_true", help="omit G1-G5 (the smoke tier is never scored for lines)")
    r.add_argument("--oracle-from", help="another run whose oracle arm is shown beside (reference only)")
    r.add_argument("--variance", help="comma-separated repeat runs of agent-policy on the main model (8.4)")
    r.add_argument("--haystacks", help="comma-separated haystack keys: restrict every arm to them (a run on part of a tier)")
    a = sub.add_parser("agy", help="LLM arms through the Antigravity CLI over real MCP stdio")
    a.add_argument("--tier", default="smoke")
    a.add_argument("--arms", default=",".join(LLM_ARMS))
    a.add_argument("--models", required=True)
    a.add_argument("--run", required=True)
    a.add_argument("--haystacks", help="comma-separated haystack keys (default: the whole tier)")
    a.add_argument("--max-sessions", type=int, help="stop each haystack after this many sessions (plumbing checks)")
    a.add_argument("--jobs", type=int, default=1, help="haystacks run at once (each runs its sessions in order)")
    a.add_argument("--effort", default="medium")
    a.add_argument("--no-freeze-check", action="store_true", help="allow a non-smoke run that doesn't match the freeze (record why)")
    a.add_argument("--quota-gate", action="store_true", help="pause new sessions while the CLI's quota is low (tier1 always does)")
    rt = sub.add_parser("retrace", help="recompute the trace-vs-proxy check of a run's LLM sessions from the saved files")
    rt.add_argument("--run", required=True)
    pj = sub.add_parser("project", help="tier-1 runtime and token projection from a smoke run")
    pj.add_argument("--run", required=True)
    c = sub.add_parser("levels", help="value-based vs card-level judgments for flat and oracle")
    c.add_argument("--run", required=True)
    c.add_argument("--write", help="also write results/<NAME>.md")
    t1 = sub.add_parser("tier1", help="run tier 1 as frozen: the matrix, then the variance repeats, behind the quota gate")
    t1.add_argument("--jobs", type=int, default=12, help="haystacks run at once")
    t1.add_argument("--dry-run", action="store_true", help="print the schedule and exit")
    t1.add_argument("--only", choices=("main", "variance"), help="only the matrix (tier1/) or only the variance repeats (tier1-var*/)")
    t1.add_argument("--release-variance", action="store_true", help="remove the deferral markers of the variance repeats")
    sub.add_parser("prompts", help="print the prompts' SHA-256 digests")
    au = sub.add_parser("audit", help="value-matching audit worksheets (6.3) for a run's agent arms, or tally filled verdicts")
    au.add_argument("--run", required=True)
    au.add_argument("--tally", action="store_true", help="count verdicts in results/audit/<run>/*.json")
    f = sub.add_parser("freeze", help="write results/freeze.json (what PLAN.md freezes); tier 1 refuses to run if it changes")
    f.add_argument("--check", action="store_true", help="only compare the current state with results/freeze.json")
    args = p.parse_args(argv)
    data = sources.data_dir(args.data)
    root = runs_root(args.runs)

    if args.command == "prompts":
        print(json.dumps(digests(), indent=1))
        return 0
    if args.command == "offline":
        run = root / args.run
        run.mkdir(parents=True, exist_ok=True)
        offline(args.tier, [a for a in args.arms.split(",") if a], run, args.jobs, data, log=lambda s: print(s, file=sys.stderr))
        return 0
    if args.command == "gate":
        arms = load_run(root / args.run)
        report = render_gate(gate(arms), summarize(arms))
        print(report)
        if args.write:
            (RESULTS / "gate1.md").write_text(report, encoding="utf-8")
        return 0
    if args.command == "report":
        arms = load_run(root / args.run)
        if args.flat_from and "flat" not in arms:
            arms["flat"] = load_arm(root / args.flat_from / "flat")
        if args.oracle_from and "oracle" not in arms:
            arms["oracle"] = load_arm(root / args.oracle_from / "oracle")
        if args.run.startswith("tier1"):  # tier 1 as run: the dropped haystacks are out of every arm (PLAN.md)
            arms = {a: [r for r in recs if r.get("haystack") not in TIER1_DROPPED] for a, recs in arms.items()}
        if args.haystacks:
            keep = set(args.haystacks.split(","))
            arms = {a: [r for r in recs if r.get("haystack") in keep] for a, recs in arms.items()}
        summary = summarize(arms)
        adir = RESULTS / "audit" / args.run
        if adir.is_dir():
            from . import audit as auditmod

            from . import audit2

            summary["audit"] = {}
            for vp in sorted(adir.glob("*.json")):
                v = json.loads(vp.read_text(encoding="utf-8"))
                if vp.stem in arms and "passes" in v["cases"]:  # matcher v2: audited both ways
                    summary["audit"][vp.stem] = {"tally": audit2.tally(v), "corrected": audit2.corrected(arms[vp.stem], v),
                                                 "two_way": True}
                elif vp.stem in arms:
                    summary["audit"][vp.stem] = {"tally": auditmod.tally(v), "corrected": audit_corrected(arms[vp.stem], v)}
        if args.variance:
            key = f"agent-policy@{MAIN_MODEL}"
            reps = [load_arm(root / r / key) for r in args.variance.split(",") if r]
            summary["variance"] = variance(arms.get(key, []), reps, variance_episodes(data))
        if args.no_lines:
            for a in summary["arms"].values():
                a.pop("lines", None)
        report = render_run(args.run, summary)
        print(report)
        if args.write:
            RESULTS.mkdir(exist_ok=True)
            (RESULTS / f"{args.write}.md").write_text(report, encoding="utf-8")
            (RESULTS / f"{args.write}.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
        return 0
    if args.command == "retrace":
        print(json.dumps(retrace(root / args.run)))
        return 0
    if args.command == "project":
        print(json.dumps(projection(load_run(root / args.run), "1", data), indent=1))
        return 0
    if args.command == "levels":
        from .report import render_levels

        report = render_levels(args.run, compare_levels(load_run(root / args.run)))
        print(report)
        if args.write:
            (RESULTS / f"{args.write}.md").write_text(report, encoding="utf-8")
        return 0
    if args.command == "audit":
        from . import audit

        out = RESULTS / "audit" / args.run
        out.mkdir(parents=True, exist_ok=True)
        if args.tally:
            rows = {p.stem: audit.tally(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(out.glob("*.json"))}
            print(json.dumps(rows, indent=1))
            (out / "tally.txt").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
            return 0
        for arm in sorted(p for p in (root / args.run).iterdir() if p.is_dir() and p.name.startswith("agent-")):
            target = out / f"{arm.name}.json"
            if target.exists():
                print(f"{target} exists (verdicts kept); delete it to resample")
                continue
            ws = audit.worksheet(arm)
            target.write_text(json.dumps(ws, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            (out / f"{arm.name}.md").write_text(audit.render(ws), encoding="utf-8")
            print(arm.name, ws["population"])
        return 0
    if args.command == "freeze":
        if args.check:
            problems = check_freeze(data)
            print("\n".join(problems) or "matches the freeze")
            return 1 if problems else 0
        facts = frozen_facts(data)
        RESULTS.mkdir(exist_ok=True)
        FREEZE.write_text(json.dumps(facts, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in facts.items() if k != "tiers"}, indent=1))
        return 0
    if args.command == "tier1":
        from . import agy

        work = tier1_work(root, data)
        if args.only == "main":
            work = [w for w in work if w[0].name == "tier1"]
        elif args.only == "variance":
            work = [w for w in work if w[0].name.startswith("tier1-var")]
            deferred = [w for w in work if _deferred(arm_dir(w[0], w[1], w[2]) / slug(w[3].key))]
            if deferred and not args.dry_run:
                print(f"{len(deferred)} variance items are still marked deferred; remove the markers first "
                      "(python -m evals.agent tier1 --release-variance)", file=sys.stderr)
                return 2
        if args.release_variance:
            n = 0
            for run, a, m, h in tier1_work(root, data):
                d = arm_dir(run, a, m) / slug(h.key)
                if run.name.startswith("tier1-var") and _deferred(d):
                    (d / "records.jsonl").unlink()
                    n += 1
            print(f"released {n} deferred variance items")
            return 0
        if args.dry_run:
            for i, (run, a, m, h) in enumerate(work):
                print(i, run.name, f"{a}@{m}", h.key)
            return 0
        problems = check_freeze(data)
        if problems:
            print("refusing to run tier 1\n" + "\n".join(problems), file=sys.stderr)
            return 2
        log = lambda s: print(time.strftime("%H:%M:%S ") + s, file=sys.stderr, flush=True)
        gate = agy.QuotaGate(log_path=root / "tier1" / "quota.jsonl", log=log)
        (root / "tier1").mkdir(parents=True, exist_ok=True)
        return agy.run_work(work, args.jobs, "medium", gate, None, {"tier": "1", "matrix": [list(c) for c in MATRIX]})
    if args.command == "agy":
        if args.tier != "smoke" and not args.no_freeze_check:
            problems = check_freeze(data)
            outside = [f"{a}@{m}" for a in args.arms.split(",") if a for m in args.models.split(",") if m
                       and (a, m) not in MATRIX]
            if outside:
                problems.append("not in the frozen tier-1 matrix: " + ", ".join(outside))
            if problems:
                print("refusing to run tier", args.tier, "\n" + "\n".join(problems), file=sys.stderr)
                return 2
        from .agy import run_tier

        return run_tier(args, data, root / args.run)
    return 2
