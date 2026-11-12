"""Tool dispatch for in-process agents (the scripted ones), and the per-call log shared with the MCP proxy.

``Dispatcher`` answers a tool call exactly as the MCP server's ``tools/call`` does (``MCPServer._tools_call``:
the JSON text of the result, ``isError`` for engine errors), counts calls against the session cap
(agent_test.md 4.5: at most 40), and logs each one. ``summarize_calls`` turns a log (from here or from
``mcp_proxy``) into the per-session telemetry of 6.2: operation mix, lineage fields, errors, cap.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from mindslice import Workspace
from mindslice.interfaces.mcp_server import MCPServer

CAP = 40
CAP_MESSAGE = ("tool-call limit reached: at most {cap} tool calls per session. This session is over; "
               "no further calls will run. Reply DONE.")


def cap_result(cap: int) -> dict[str, Any]:
    payload = {"error": "CallLimit", "message": CAP_MESSAGE.format(cap=cap)}
    return {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": True}


class JsonlLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "a", encoding="utf-8")

    def write(self, row: dict[str, Any]) -> None:
        self._fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


class Dispatcher:
    def __init__(self, ws: Workspace, log: JsonlLog | None, session: int, cap: int | None = CAP, **context: Any) -> None:
        self.server = MCPServer(ws)
        self.log = log
        self.session = session
        self.cap = cap
        self.context = context
        self.calls = 0
        self.cap_hit = False

    def __call__(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        t0 = time.perf_counter()
        if self.cap is not None and self.calls > self.cap:
            self.cap_hit = True
            result, refused = cap_result(self.cap), True
        else:
            result, refused = self.server._tools_call({"name": name, "arguments": arguments}), False
        row = {**self.context, "session": self.session, "seq": self.calls, "tool": name, "arguments": arguments,
               "result": result["content"][0]["text"], "is_error": bool(result.get("isError")), "refused": refused,
               "latency_ms": round((time.perf_counter() - t0) * 1000, 2), "t": time.time()}
        if self.log is not None:
            self.log.write(row)
        return result

    def payload(self, result: dict[str, Any]) -> dict[str, Any]:
        return json.loads(result["content"][0]["text"])


def summarize_calls(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ops: dict[str, int] = {}
    tools: dict[str, int] = {}
    sup = ext = errors = refused = 0
    for r in rows:
        tools[r["tool"]] = tools.get(r["tool"], 0) + 1
        if r.get("refused"):
            refused += 1
            continue
        if r.get("is_error"):
            errors += 1
        if r["tool"] == "write":
            a = r.get("arguments") or {}
            op = a.get("op", "create")
            ops[op] = ops.get(op, 0) + 1
            if not r.get("is_error"):
                sup += bool(a.get("supersedes"))
                ext += bool(a.get("extends"))
    return {"tool_calls": len(rows), "tools": tools, "ops": ops, "with_supersedes": sup, "with_extends": ext,
            "tool_errors": errors, "refused": refused, "cap_hit": refused > 0}
