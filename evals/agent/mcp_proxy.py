"""A thin MCP stdio wrapper around ``python -m mindslice -w <workspace> mcp`` (agent_test.md 4.1, 4.5).

    python -m evals.agent.mcp_proxy --workspace WS --log calls.jsonl --session 3 --cap 40 [--context JSON]

The MCP client (here the Antigravity CLI) talks to this process; it forwards every JSON-RPC message
unchanged to the shipped MindSlice server, a child process, and relays the answers unchanged. It adds two
things and changes nothing else:

* **Logging.** Every message is logged to ``--log`` as JSONL; each ``tools/call`` with its arguments,
  result text, ``isError`` and latency (the same row shape as ``tools.Dispatcher``).
* **The call cap.** The first ``--cap`` ``tools/call`` requests are forwarded; later ones get a tool error
  (``CallLimit``) without reaching the server, and ``<log>.cap`` is created so the runner can end the
  session (hitting the cap ends it).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .tools import cap_result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.agent.mcp_proxy")
    p.add_argument("--workspace", required=True)
    p.add_argument("--log", required=True)
    p.add_argument("--session", type=int, default=0)
    p.add_argument("--cap", type=int, default=40)
    p.add_argument("--context", default="{}", help="JSON object added to every log row")
    args = p.parse_args(argv)
    for stream in (sys.stdin, sys.stdout):
        stream.reconfigure(encoding="utf-8")
    context = json.loads(args.context)
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "a", encoding="utf-8")
    cap_flag = log_path.with_name(log_path.name + ".cap")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    child = subprocess.Popen([sys.executable, "-m", "mindslice", "-w", args.workspace, "mcp"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, env=env, text=True, encoding="utf-8", bufsize=1)
    calls = 0

    def emit(row: dict) -> None:
        log.write(json.dumps({**context, "session": args.session, **row, "t": time.time()}, ensure_ascii=False) + "\n")
        log.flush()

    def forward(message) -> str | None:
        """Send one message to the server; read its one-line answer when the message expects one."""
        child.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        child.stdin.flush()
        expects = any("id" in m for m in message) if isinstance(message, list) else (isinstance(message, dict) and "id" in message)
        if not expects:
            return None
        return child.stdout.readline()

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                answer = forward_raw(child, line)
                if answer:
                    sys.stdout.write(answer)
                    sys.stdout.flush()
                continue
            method = message.get("method") if isinstance(message, dict) else "batch"
            if method == "tools/call":
                calls += 1
                params = message.get("params") or {}
                t0 = time.perf_counter()
                if calls > args.cap:
                    cap_flag.touch()
                    result = cap_result(args.cap)
                    answer = json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "result": result}) + "\n"
                    refused = True
                else:
                    answer = forward(message)
                    refused = False
                latency = round((time.perf_counter() - t0) * 1000, 2)
                try:
                    res = json.loads(answer).get("result") or {}
                except (json.JSONDecodeError, AttributeError):
                    res = {}
                content = res.get("content") or [{}]
                emit({"kind": "tools/call", "seq": calls, "tool": params.get("name"), "arguments": params.get("arguments") or {},
                      "result": content[0].get("text"), "is_error": bool(res.get("isError")), "refused": refused,
                      "latency_ms": latency})
            else:
                answer = forward(message)
                emit({"kind": "rpc", "method": method, "request": message,
                      "response": json.loads(answer) if answer else None})
            if answer:
                sys.stdout.write(answer if answer.endswith("\n") else answer + "\n")
                sys.stdout.flush()
    finally:
        try:
            child.stdin.close()
            child.wait(timeout=10)
        except Exception:  # pragma: no cover - shutdown
            child.kill()
        log.close()
    return 0


def forward_raw(child: subprocess.Popen, line: str) -> str | None:
    child.stdin.write(line + "\n")
    child.stdin.flush()
    return child.stdout.readline()


if __name__ == "__main__":
    sys.exit(main())
