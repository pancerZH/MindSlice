"""The LLM arms through the Antigravity CLI (``agy``), over real MCP stdio (agent_test.md 4.1, first bullet).

Each session of a haystack is a **fresh, independent** ``agy --print`` conversation (never ``--continue``
or ``--conversation``), started in its own new working directory that holds only these customization files:

* ``.agents/plugins/mindslice-eval/``: a plugin whose ``mcp_config.json`` starts ``evals.agent.mcp_proxy``,
  the logging, capped wrapper around ``python -m mindslice -w <workspace> mcp`` for this haystack. Its four
  tools are declared ``eager``, so the model gets them as functions with the shipped schemas and
  descriptions (``mcp_mindslice-eval_mindslice_<tool>``), not behind the CLI's lazy ``call_mcp_tool``.
* ``.agents/agents/<AGENT>.md``: a custom main agent whose body is the arm's system prompt (agent_test.md
  4.2-4.4) and whose frontmatter drops the CLI's default prompt sections and built-in tools
  (``excludeDefaultComponents``). Three framework tools stay declared (``list_resources``,
  ``read_resource``, ``manage_task``; none touches files).
* ``.agents/hooks.json``: a ``PreToolUse`` hook (``evals.agent.tool_gate``) that denies every call that
  isn't an MCP tool, so those three can't run either.

The CLI's ``stream-json`` trace is kept per session and checked: no non-MCP tool call may run (denied
attempts are counted), and the traced MindSlice calls must match the ``tools/call`` requests the proxy
logged, in order. A fresh conversation sees nothing of earlier ones (checked before the smoke tier: asked
for any earlier conversation, summary or memory in its context, it answered NONE). A provider failure is retried
on the same session after restoring the workspace's ``overlay/`` (never skipped); after ``RETRIES`` the
haystack is marked failed. Hitting the 40-call cap ends the session (the proxy refuses the 41st call and
flags it; the runner stops the CLI).
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .agents import SessionOutcome, SessionTask
from .tools import CAP

AGY = os.environ.get("AGY_BIN") or shutil.which("agy") or str(Path.home() / ".local" / "bin" / "agy")
AGENT = "mindslice-memory-keeper"
PLUGIN = "mindslice-eval"
SERVER = "mindslice"
MCP_TOOLS = ("manifest", "search", "read", "write")
REPO = Path(__file__).resolve().parents[2]
FLAGS = ("--output-format", "stream-json", "--dangerously-skip-permissions", "--disable-slash-commands")
TIMEOUT_S = 1800  # one session; the CLI's own --print-timeout is left at 0 (wait for the turn)
RETRIES = 3
BACKOFF_S = (30, 120, 300)

FRONTMATTER = {
    "name": AGENT,
    "description": "Long-term memory keeper for the MindSlice agent-in-the-loop lineage test (evals/agent).",
    "mainAgent": True,
    "subagent": False,
    "excludeDefaultComponents": True,
}


def _yaml(v: Any) -> str:
    return json.dumps(v)  # JSON scalars and lists are valid YAML flow values


def agent_markdown(system_prompt: str, frontmatter: dict[str, Any] | None = None) -> str:
    fm = {**FRONTMATTER, **(frontmatter or {})}
    head = "\n".join(f"{k}: {_yaml(v)}" for k, v in fm.items())
    return f"---\n{head}\n---\n{system_prompt}\n"


def write_config(cwd: Path, system_prompt: str, workspace: Path, log: Path, session: int, cap: int,
                 context: dict[str, Any], frontmatter: dict[str, Any] | None = None) -> None:
    plugin = cwd / ".agents" / "plugins" / PLUGIN
    (plugin).mkdir(parents=True, exist_ok=True)
    (cwd / ".agents" / "agents").mkdir(parents=True, exist_ok=True)
    (plugin / "plugin.json").write_text(json.dumps({"name": PLUGIN}) + "\n", encoding="utf-8")
    args = ["-m", "evals.agent.mcp_proxy", "--workspace", str(workspace), "--log", str(log), "--session", str(session),
            "--cap", str(cap), "--context", json.dumps(context)]
    # Eager tools are declared to the model as functions with the shipped schemas and descriptions (not
    # behind the CLI's lazy call_mcp_tool dispatcher).
    config = {"mcpServers": {SERVER: {"command": sys.executable, "args": args, "cwd": str(REPO),
                                      "env": {"PYTHONPATH": str(REPO), "PYTHONIOENCODING": "utf-8"},
                                      "tools": {t: {"eager": True} for t in MCP_TOOLS}}}}
    (plugin / "mcp_config.json").write_text(json.dumps(config, indent=1) + "\n", encoding="utf-8")
    (cwd / ".agents" / "agents" / f"{AGENT}.md").write_text(agent_markdown(system_prompt, frontmatter), encoding="utf-8")
    gate = f"cd {shlex.quote(str(REPO))} && {shlex.quote(sys.executable)} -m evals.agent.tool_gate --log {shlex.quote(str(cwd.parent / (cwd.name + '.gate.jsonl')))}"
    hooks = {"mindslice-tool-gate": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": gate, "timeout": 30}]}]}}
    (cwd / ".agents" / "hooks.json").write_text(json.dumps(hooks, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# The stream-json trace
# ---------------------------------------------------------------------------


def read_stream(path: Path) -> list[dict[str, Any]]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"event": "unparsed", "text": line[:2000]})
    return out


def _walk(x: Any):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from _walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk(v)


def tool_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tool invocations in the trace: ``step_update`` events with ``step_type == "tool"`` (an ACTIVE and a
    DONE event per call, keyed by step index)."""
    calls: dict[tuple, dict[str, Any]] = {}
    for e in events:
        st = e.get("step_update")
        if not isinstance(st, dict) or st.get("step_type") != "tool":
            continue
        info = st.get("tool_info") or {}
        key = (st.get("conversation_id"), st.get("step_index"))
        c = calls.setdefault(key, {"step": st.get("step_index"), "name": st.get("tool_name") or info.get("name"), "states": []})
        c["states"].append(st.get("state"))
        if st.get("state") in ("DONE", "ERROR"):
            c["duration_s"] = st.get("duration_seconds")
            err = info.get("error")
            if err:
                c["error"] = (err.get("message") if isinstance(err, dict) else str(err)) or ""
    return list(calls.values())


def rejected_by_cli(call: dict[str, Any]) -> bool:
    """A call that failed inside the CLI and never reached a server: its error is the CLI's plain text
    ("invalid arguments", "unknown tool", "denied by pre-tool hook"), not the server's JSON error payload."""
    if not call["states"] or call["states"][-1] != "ERROR":
        return False
    try:
        payload = json.loads(call.get("error") or "")
    except (json.JSONDecodeError, TypeError):
        return True
    return not (isinstance(payload, dict) and "error" in payload)


def error_steps(events: list[dict[str, Any]]) -> int:
    return sum(1 for e in events if (e.get("step_update") or {}).get("step_type") == "error_message")


def mcp_name(name: str | None) -> str | None:
    """The MindSlice tool a trace name is (the CLI names plugin MCP tools ``mcp_<plugin>_<server>_<tool>``)."""
    for t in MCP_TOOLS:
        if name == f"mcp_{PLUGIN}_{SERVER}_{t}":
            return t
    return None


def trace_check(traced: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Do the CLI's trace and the proxy's log tell the same story?

    Set aside the calls the CLI rejected itself (``rejected_by_cli``) and those still running when it was
    stopped; the remaining traced MindSlice calls
    must be exactly the proxy's ``tools/call`` requests, in order, except that refused calls still in flight
    when the CLI was stopped at the cap may be missing from the trace.
    """
    mcp = [c for c in traced if mcp_name(c["name"])]
    # Served: finished (DONE, or ERROR with the server's payload); not rejected by the CLI, and not still
    # ACTIVE when the CLI was stopped (at the cap or a timeout).
    served = [mcp_name(c["name"]) for c in mcp if c["states"] and c["states"][-1] in ("DONE", "ERROR") and not rejected_by_cli(c)]
    tools = [r["tool"] for r in rows]
    leftover = rows[len(served):]
    ok = served == tools[:len(served)] and all(r.get("refused") for r in leftover)
    return {"ok": ok, "client_rejected": len(mcp) - len(served), "untraced_refused": len(leftover)}


def result_of(events: list[dict[str, Any]]) -> dict[str, Any]:
    for e in reversed(events):
        if e.get("event") == "result" or e.get("type") == "result":
            return e.get("result") if isinstance(e.get("result"), dict) else e
    return {}


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------


class AgyAgent:
    tools = True

    def __init__(self, arm: str, model: str, effort: str = "medium", cap: int = CAP, timeout_s: int = TIMEOUT_S,
                 retries: int = RETRIES, frontmatter: dict[str, Any] | None = None, backoff=BACKOFF_S) -> None:
        self.arm, self.model, self.effort, self.cap = arm, model, effort, cap
        self.timeout_s, self.retries, self.frontmatter, self.backoff = timeout_s, retries, frontmatter, backoff

    def command(self, message: str) -> list[str]:
        return [AGY, f"--print={message}", "--model", self.model, "--effort", self.effort, "--agent", AGENT, *FLAGS]

    def run_session(self, task: SessionTask, call=None) -> SessionOutcome:
        i = task.session.index
        sdir = task.workdir / "agy" / f"s{i:03d}"
        if sdir.exists():
            shutil.rmtree(sdir)
        sdir.mkdir(parents=True)
        overlay = task.ws.root / "overlay"
        backup = sdir / "overlay.before"
        shutil.copytree(overlay, backup)
        log = task.workdir / "calls.jsonl"
        attempts = []
        for attempt in range(self.retries + 1):
            if attempt:
                shutil.rmtree(overlay)
                shutil.copytree(backup, overlay)
                time.sleep(self.backoff[min(attempt - 1, len(self.backoff) - 1)])
            outcome = self._attempt(task, sdir, log, attempt)
            attempts.append({k: outcome.meta.get(k) for k in ("exit_code", "status", "finished_reason", "error", "wall_s")})
            if not outcome.failed or outcome.meta.get("fatal"):
                break
        outcome.meta["attempts"] = attempts
        outcome.meta["retries"] = len(attempts) - 1
        shutil.rmtree(backup, ignore_errors=True)
        return outcome

    def _attempt(self, task: SessionTask, sdir: Path, log: Path, attempt: int) -> SessionOutcome:
        i = task.session.index
        cwd = sdir / f"cwd{attempt}"
        context = {"haystack": task.haystack.key, "arm": self.arm, "model": self.model, "attempt": attempt}
        cap_flag = log.with_name(log.name + ".cap")
        cap_flag.unlink(missing_ok=True)
        write_config(cwd, task.system_prompt, task.ws.root, log, i, self.cap, context, self.frontmatter)
        stream = sdir / f"stream{attempt}.jsonl"
        stderr = sdir / f"stderr{attempt}.log"
        cmd = self.command(task.message)
        (sdir / f"command{attempt}.json").write_text(json.dumps(cmd[:1] + ["--print=<session message>"] + cmd[2:]) + "\n")
        t0 = time.time()
        cap_hit = timed_out = False
        with open(stream, "w", encoding="utf-8") as out, open(stderr, "w", encoding="utf-8") as err:
            proc = subprocess.Popen(cmd, cwd=cwd, stdout=out, stderr=err, stdin=subprocess.DEVNULL, start_new_session=True)
            while proc.poll() is None:
                time.sleep(0.5)
                if cap_flag.exists():
                    cap_hit = True
                    _stop(proc)
                    break
                if time.time() - t0 > self.timeout_s:
                    timed_out = True
                    _stop(proc)
                    break
            code = proc.wait()
        wall = time.time() - t0
        events = read_stream(stream)
        res = result_of(events)
        rows = [r for r in _read_jsonl(log) if r.get("kind") == "tools/call" and r.get("session") == i and r.get("attempt") == attempt]
        traced = tool_calls(events)
        gate = _read_jsonl(sdir / f"cwd{attempt}.gate.jsonl")
        # A non-MCP call the gate denied ends in state ERROR without running; any that reached DONE ran.
        non_mcp = [c["name"] for c in traced if mcp_name(c["name"]) is None and "DONE" in c["states"]]
        denied = [c["name"] for c in traced if mcp_name(c["name"]) is None and "DONE" not in c["states"]]
        check = trace_check(traced, rows)
        usage = res.get("usage") or {}
        reply = res.get("response") if isinstance(res.get("response"), str) else None
        status = res.get("status")
        meta = {"model": self.model, "effort": self.effort, "exit_code": code, "status": status,
                "finished_reason": res.get("finished_reason"), "conversation_id": res.get("conversation_id"),
                "duration_s": res.get("duration_seconds"), "num_turns": res.get("num_turns"), "wall_s": round(wall, 2),
                "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens", "thinking_tokens", "cache_read_tokens", "total_tokens")}
                | {"cached_tokens": usage.get("cache_read_tokens")},
                "traced_tool_calls": len(traced), "non_mcp_tool_calls": len(non_mcp), "non_mcp_tools": non_mcp[:10],
                "non_mcp_denied": len(denied), "non_mcp_denied_tools": denied[:10],
                "gate_denials": sum(1 for g in gate if g.get("decision") == "deny"), "gate_checks": len(gate),
                "proxy_tool_calls": len(rows), "trace_matches_proxy": check["ok"],
                "client_rejected_calls": check["client_rejected"], "error_steps": error_steps(events),
                "cap_hit": cap_hit, "timed_out": timed_out, "events": len(events)}
        failed = False
        if cap_hit:
            meta["finished_reason"] = "call_cap"
        elif timed_out:
            failed, meta["error"] = True, f"timeout after {self.timeout_s}s"
        elif code != 0 or status not in (None, "SUCCESS") or not res:
            failed = True
            meta["error"] = _error_text(events, stderr) or f"exit {code}, status {status}"
        return SessionOutcome(reply, rows, meta, failed)


def _stop(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=15)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _error_text(events: list[dict[str, Any]], stderr: Path) -> str:
    for e in reversed(events):
        if "error" in str(e.get("event") or e.get("type") or "") or e.get("error"):
            return json.dumps(e)[:600]
    try:
        return stderr.read_text(encoding="utf-8", errors="replace")[-600:]
    except OSError:
        return ""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


# ---------------------------------------------------------------------------
# A tier
# ---------------------------------------------------------------------------


def run_tier(args, data, run: Path) -> int:
    from .run import arm_dir, environment, slug
    from .runner import run_haystack
    from .sessions import tier_haystacks

    hs = tier_haystacks(args.tier, data)
    if args.haystacks:
        keep = set(args.haystacks.split(","))
        hs = [h for h in hs if h.key in keep]
    arms = [a for a in args.arms.split(",") if a]
    models = [m for m in args.models.split(",") if m]
    run.mkdir(parents=True, exist_ok=True)
    meta = {"tier": args.tier, "arms": arms, "models": models, "effort": args.effort, "agy": agy_version(),
            "flags": list(FLAGS), "agent_frontmatter": FRONTMATTER, "cap": CAP, "environment": environment(),
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    (run / f"run-{int(time.time())}.json").write_text(json.dumps(meta, indent=1) + "\n")
    lock = threading.Lock()

    def job(arm: str, model: str, h) -> str:
        out = arm_dir(run, arm, model) / slug(h.key)
        if (out / "records.jsonl").exists():
            return f"skip {arm}@{model} {h.key} (done)"
        agent = AgyAgent(arm=arm, model=model, effort=args.effort)
        if args.max_sessions:
            agent = _Limited(agent, args.max_sessions)
        t0 = time.time()
        recs = run_haystack(h, arm, out, agent=agent, log=lambda s: _print(lock, s))
        failed = next((r["failed"] for r in recs if r["kind"] == "haystack"), None)
        return f"{arm}@{model} {h.key}: {time.time() - t0:.0f}s" + (f" FAILED ({failed})" if failed else "")

    work = [(a, m, h) for m in models for a in arms for h in hs]
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futs = [pool.submit(job, *w) for w in work]
        for f in as_completed(futs):
            _print(lock, f.result())
    return 0


class _Limited:
    """Stops a haystack after ``n`` sessions (plumbing checks only; the haystack is marked failed)."""

    tools = True

    def __init__(self, agent: AgyAgent, n: int) -> None:
        self.agent, self.n = agent, n

    def run_session(self, task, call=None):
        if task.session.index >= self.n:
            return SessionOutcome(None, [], {"error": f"stopped after {self.n} sessions (--max-sessions)", "fatal": True}, True)
        return self.agent.run_session(task, call)


def _print(lock: threading.Lock, s: str) -> None:
    with lock:
        print(s, file=sys.stderr, flush=True)


def agy_version() -> str | None:
    try:
        return subprocess.run([AGY, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
