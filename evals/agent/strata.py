"""The LLM arms through a local Strata server (OpenAI-compatible ``/v1/chat/completions``), over real MCP stdio.

Each session of a haystack is a **fresh, independent** conversation: ``[system, user]`` (the arm's system
prompt and the session message, exactly as for ``agy``), then the model's turns. The MindSlice tools are
reached the same way as with ``agy``: this client starts ``evals.agent.mcp_proxy`` (the logging, capped
wrapper around ``python -m mindslice -w <workspace> mcp``) as a child process for the session and speaks
JSON-RPC 2.0 to it over stdio (``initialize``, ``tools/list``, ``tools/call``). The four tool schemas and
descriptions come from ``tools/list`` unchanged, converted to OpenAI ``tools``; nothing else is offered, so
the model has no other tool. A call to any other name, or with arguments that aren't a JSON object, is not
forwarded: the model gets an error result, and the session counts it (``non_mcp_denied``,
``client_rejected_calls``), as the CLI's rejections are counted for ``agy``.

The loop: append the assistant message (``content``, ``reasoning_content``, ``tool_calls``), run every
tool call in order through the proxy, append each result as a ``tool`` message, ask again. It ends when the
model answers without tool calls (its reply, normally ``DONE``), when the proxy refuses a call past the
40-call cap (``cap_hit``: the session stops at once, as with ``agy``), at ``MAX_TURNS`` model turns, or at
the session timeout. An HTTP or connection failure is retried on the same session after restoring the
workspace's ``overlay/`` (never skipped); after ``RETRIES`` the haystack is marked failed.

Telemetry per session, in ``agy``'s keys: ``usage.input_tokens`` (uncached prompt tokens, summed over the
turns), ``cached_tokens`` and ``cache_read_tokens`` (prompt tokens served from the KV cache), ``output_tokens``
(completion tokens, reasoning included), ``reasoning_chars``, and Strata's ``timings`` summed. Every model
response is kept in ``strata/sNNN/chatK.jsonl``. Only the standard library is used.

Strata serves one sequence at a time: run with ``--jobs 1``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from .agents import SessionOutcome, SessionTask
from .tools import CAP

URL = os.environ.get("STRATA_URL", "http://127.0.0.1:8080")
MODEL = "qwen3.8-flash-next-iq3_s"
# Sampling: Strata's own defaults for this model (GET /props, 2026-11-08), sent explicitly so a server-side
# change can't alter a run; max_tokens bounds one turn (the server's default is unlimited).
SAMPLING = {"temperature": 1.0, "top_p": 0.95, "top_k": 20}
MAX_TOKENS = 32768
MAX_TURNS = 80  # model turns per session (the 40-call cap normally ends a runaway session first)
TIMEOUT_S = 3600  # one session
HTTP_TIMEOUT_S = 1200  # one request
RETRIES = 3
BACKOFF_S = (10, 60, 180)
PROTOCOL = "2024-11-05"
REPO = Path(__file__).resolve().parents[2]


class StrataError(RuntimeError):
    """A failed request to the server (connection, HTTP status, or a malformed answer)."""


def post_json(url: str, body: dict[str, Any], timeout: float = HTTP_TIMEOUT_S) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise StrataError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise StrataError(f"{type(exc).__name__}: {exc}") from exc


def get_json(url: str, timeout: float = 30) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise StrataError(f"{type(exc).__name__}: {exc}") from exc


class MCPClient:
    """JSON-RPC 2.0 over stdio to ``evals.agent.mcp_proxy`` (which forwards to the shipped MindSlice server)."""

    def __init__(self, workspace: Path, log: Path, session: int, cap: int, context: dict[str, Any]) -> None:
        cmd = [sys.executable, "-m", "evals.agent.mcp_proxy", "--workspace", str(workspace), "--log", str(log),
               "--session", str(session), "--cap", str(cap), "--context", json.dumps(context)]
        env = {**os.environ, "PYTHONPATH": str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""), "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(cmd, cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True,
                                     encoding="utf-8", bufsize=1)
        self._id = 0

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise StrataError(f"MCP server closed during {method}")
        msg = json.loads(line)
        if "error" in msg:
            raise StrataError(f"MCP {method}: {msg['error']}")
        return msg.get("result") or {}

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}}) + "\n")
        self.proc.stdin.flush()

    def start(self) -> list[dict[str, Any]]:
        self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                    "clientInfo": {"name": "mindslice-eval-strata", "version": "1"}})
        self.notify("notifications/initialized")
        return self.request("tools/list").get("tools", [])

    def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        res = self.request("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(c.get("text", "") for c in res.get("content") or [] if c.get("type", "text") == "text")
        return text, bool(res.get("isError"))

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=20)
        except Exception:  # pragma: no cover - shutdown
            self.proc.kill()
            self.proc.wait()
        finally:
            self.proc.stdout.close()


def openai_tools(mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                              "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}}
            for t in mcp_tools]


def _assistant(msg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant", "content": msg.get("content")}
    if msg.get("reasoning_content"):
        out["reasoning_content"] = msg["reasoning_content"]
    if msg.get("tool_calls"):
        out["tool_calls"] = msg["tool_calls"]
    return out


class StrataAgent:
    tools = True

    def __init__(self, arm: str, model: str = MODEL, url: str = URL, cap: int = CAP, timeout_s: int = TIMEOUT_S,
                 retries: int = RETRIES, max_turns: int = MAX_TURNS, sampling: dict[str, Any] | None = None,
                 max_tokens: int = MAX_TOKENS, backoff=BACKOFF_S, post: Callable[..., dict[str, Any]] = post_json) -> None:
        self.arm, self.model, self.url, self.cap = arm, model, url.rstrip("/"), cap
        self.timeout_s, self.retries, self.max_turns, self.backoff = timeout_s, retries, max_turns, backoff
        self.sampling = dict(SAMPLING if sampling is None else sampling)
        self.max_tokens, self.post = max_tokens, post

    def run_session(self, task: SessionTask, call=None) -> SessionOutcome:
        i = task.session.index
        sdir = task.workdir / "strata" / f"s{i:03d}"
        if sdir.exists():
            shutil.rmtree(sdir)
        sdir.mkdir(parents=True)
        overlay = task.ws.root / "overlay"
        backup = sdir / "overlay.before"
        shutil.copytree(overlay, backup)
        log = task.workdir / "calls.jsonl"
        attempts: list[dict[str, Any]] = []
        attempt = 0
        while True:
            if attempt:
                shutil.rmtree(overlay)
                shutil.copytree(backup, overlay)
            outcome = self._attempt(task, sdir, log, attempt)
            attempts.append({k: outcome.meta.get(k) for k in ("finished_reason", "error", "wall_s")})
            if not outcome.failed or attempt >= self.retries:
                break
            time.sleep(self.backoff[min(attempt, len(self.backoff) - 1)])
            attempt += 1
        outcome.meta["attempts"] = attempts
        outcome.meta["retries"] = attempt
        shutil.rmtree(backup, ignore_errors=True)
        return outcome

    def _attempt(self, task: SessionTask, sdir: Path, log: Path, attempt: int) -> SessionOutcome:
        i = task.session.index
        context = {"haystack": task.haystack.key, "arm": self.arm, "model": self.model, "attempt": attempt}
        cap_flag = log.with_name(log.name + ".cap")
        cap_flag.unlink(missing_ok=True)
        chat = open(sdir / f"chat{attempt}.jsonl", "w", encoding="utf-8")
        t0 = time.time()
        usage = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0}
        timings = {"prompt_ms": 0.0, "predicted_ms": 0.0, "cache_n": 0, "prompt_n": 0, "predicted_n": 0,
                   "draft_n": 0, "draft_n_accepted": 0}
        sent: list[tuple[str, Any]] = []
        reply = None
        finished = "stop"
        error = None
        turns = denied = rejected = reasoning_chars = 0
        cap_hit = timed_out = False
        denied_names: list[str] = []
        mcp = MCPClient(task.ws.root, log, i, self.cap, context)
        try:
            names = set()
            tools = openai_tools(mcp_tools := mcp.start())
            names = {t["name"] for t in mcp_tools}
            messages: list[dict[str, Any]] = [{"role": "system", "content": task.system_prompt},
                                              {"role": "user", "content": task.message}]
            while True:
                if turns >= self.max_turns:
                    finished = "turn_limit"
                    break
                if time.time() - t0 > self.timeout_s:
                    timed_out, finished = True, "timeout"
                    break
                body = {"model": self.model, "messages": messages, "tools": tools, "max_tokens": self.max_tokens, **self.sampling}
                ts = time.time()
                resp = self.post(self.url + "/v1/chat/completions", body)
                turns += 1
                try:
                    choice = resp["choices"][0]
                    msg = choice["message"]
                except (KeyError, IndexError, TypeError) as exc:
                    raise StrataError(f"malformed answer: {json.dumps(resp)[:300]}") from exc
                u = resp.get("usage") or {}
                cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
                usage["input_tokens"] += int(u.get("prompt_tokens") or 0) - cached
                usage["cached_tokens"] += cached
                usage["output_tokens"] += int(u.get("completion_tokens") or 0)
                for k in timings:
                    timings[k] += (resp.get("timings") or {}).get(k) or 0
                reasoning_chars += len(msg.get("reasoning_content") or "")
                chat.write(json.dumps({"turn": turns, "latency_s": round(time.time() - ts, 2), "finish_reason": choice.get("finish_reason"),
                                       "message": msg, "usage": u, "timings": resp.get("timings")}, ensure_ascii=False) + "\n")
                chat.flush()
                messages.append(_assistant(msg))
                calls = msg.get("tool_calls") or []
                if not calls:
                    reply = msg.get("content")
                    if choice.get("finish_reason") == "length":
                        finished = "length"
                    break
                for tc in calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name")
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                        bad_args = not isinstance(args, dict)
                    except json.JSONDecodeError:
                        args, bad_args = None, True
                    if name not in names:
                        denied += 1
                        denied_names.append(str(name))
                        text = f"Unknown tool {name!r}: the only tools are {', '.join(sorted(names))}."
                    elif bad_args:
                        rejected += 1
                        text = "Invalid arguments: a JSON object matching the tool's input schema is required."
                    else:
                        sent.append((name, args))
                        text, _ = mcp.call(name, args)
                        if cap_flag.exists():
                            cap_hit, finished = True, "call_cap"
                            break
                    messages.append({"role": "tool", "tool_call_id": tc.get("id") or f"call_{turns}", "content": text})
                if cap_hit:
                    break
        except StrataError as exc:
            error, finished = str(exc), "error"
        finally:
            mcp.close()
            chat.close()
        wall = time.time() - t0
        rows = [r for r in _read_jsonl(log) if r.get("kind") == "tools/call" and r.get("session") == i and r.get("attempt") == attempt]
        matches = [(r.get("tool"), r.get("arguments")) for r in rows] == [(n, a) for n, a in sent]
        meta = {"model": self.model, "url": self.url, "sampling": self.sampling, "max_tokens": self.max_tokens,
                "finished_reason": finished, "num_turns": turns, "wall_s": round(wall, 2),
                "usage": usage | {"cache_read_tokens": usage["cached_tokens"], "thinking_tokens": None,
                                  "total_tokens": usage["input_tokens"] + usage["cached_tokens"] + usage["output_tokens"]},
                "reasoning_chars": reasoning_chars, "timings": {k: round(v, 1) for k, v in timings.items()},
                "traced_tool_calls": len(sent) + denied + rejected, "non_mcp_tool_calls": 0, "non_mcp_tools": [],
                "non_mcp_denied": denied, "non_mcp_denied_tools": denied_names[:10], "proxy_tool_calls": len(rows),
                "trace_matches_proxy": matches, "client_rejected_calls": rejected, "cap_hit": cap_hit, "timed_out": timed_out}
        failed = error is not None or timed_out
        if error:
            meta["error"] = error
        elif timed_out:
            meta["error"] = f"timeout after {self.timeout_s}s"
        return SessionOutcome(reply, rows, meta, failed)


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


def server_info(url: str = URL) -> dict[str, Any]:
    """What the server says about itself (recorded with each run and in the freeze)."""
    models = get_json(url.rstrip("/") + "/v1/models")
    props = {}
    try:
        p = get_json(url.rstrip("/") + "/props")
        props = {"default_generation_settings": p.get("default_generation_settings"), "total_slots": p.get("total_slots"),
                 "model_alias": p.get("model_alias")}
    except StrataError:
        pass
    return {"models": [{"id": m.get("id"), "meta": m.get("meta")} for m in models.get("data", [])], **props}


# ---------------------------------------------------------------------------
# A tier
# ---------------------------------------------------------------------------


def run_work(work: list[tuple[Path, str, str, Any]], jobs: int = 1, url: str = URL, max_sessions: int | None = None,
             meta: dict[str, Any] | None = None, agent_factory: Callable[..., Any] | None = None) -> int:
    """Run (run directory, arm, model, haystack) items in the order given, ``jobs`` haystacks at a time (Strata has
    one slot: 1). Done haystacks (``records.jsonl`` present) are skipped, so a stopped run resumes."""
    from .run import arm_dir, environment, slug
    from .runner import run_haystack

    lock = threading.Lock()
    stamp = int(time.time())
    try:
        server = server_info(url)
    except StrataError as exc:
        server = {"error": str(exc)}
    for run in dict.fromkeys(w[0] for w in work):
        run.mkdir(parents=True, exist_ok=True)
        info = {"items": sum(1 for w in work if w[0] == run), "client": "strata", "url": url, "server": server,
                "sampling": SAMPLING, "max_tokens": MAX_TOKENS, "max_turns": MAX_TURNS, "cap": CAP, "jobs": jobs,
                "environment": environment(), "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **(meta or {})}
        (run / f"run-{stamp}.json").write_text(json.dumps(info, indent=1) + "\n")
    failures = 0
    make = agent_factory or (lambda arm, model: StrataAgent(arm=arm, model=model, url=url))

    def job(run: Path, arm: str, model: str, h) -> str:
        out = arm_dir(run, arm, model) / slug(h.key)
        if (out / "records.jsonl").exists():
            return f"skip {run.name} {arm}@{model} {h.key} (done)"
        agent = make(arm, model)
        if max_sessions:
            agent = _Limited(agent, max_sessions)
        t0 = time.time()
        recs = run_haystack(h, arm, out, agent=agent, log=lambda s: _print(lock, f"{run.name} {model} {s}"))
        failed = next((r["failed"] for r in recs if r["kind"] == "haystack"), None)
        return f"{run.name} {arm}@{model} {h.key}: {time.time() - t0:.0f}s" + (f" FAILED ({failed})" if failed else "")

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futs = [pool.submit(job, *w) for w in work]
        for f in as_completed(futs):
            try:
                line = f.result()
            except Exception as exc:  # a crash in one haystack must not stop the others
                failures += 1
                line = f"ERROR {type(exc).__name__}: {exc}"
            failures += "FAILED" in line
            _print(lock, line)
    return 1 if failures else 0


class _Limited:
    """Stops a haystack after ``n`` sessions (plumbing checks only; the haystack is marked failed)."""

    tools = True

    def __init__(self, agent, n: int) -> None:
        self.agent, self.n = agent, n

    def run_session(self, task, call=None):
        if task.session.index >= self.n:
            return SessionOutcome(None, [], {"error": f"stopped after {self.n} sessions (--max-sessions)", "fatal": True}, True)
        return self.agent.run_session(task, call)


def _print(lock: threading.Lock, s: str) -> None:
    with lock:
        print(s, file=sys.stderr, flush=True)
