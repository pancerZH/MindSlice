"""The CLI's ``PreToolUse`` hook for the LLM arms: only MCP tool calls run (agent_test.md 4.1).

The custom agent already drops the CLI's built-in tools (``excludeDefaultComponents``); three framework
tools remain declared (``list_resources``, ``read_resource``, ``manage_task``). This hook denies every
tool call that isn't an MCP tool, so the agent can use nothing but the MindSlice server, and logs each
decision (``--log``) so the runner can count attempts.

    python -m evals.agent.tool_gate --log gate.jsonl     # reads the hook payload on stdin
"""

from __future__ import annotations

import argparse
import json
import sys
import time

REASON = "Only the four MindSlice tools (manifest, search, read, write) are available in this session."


def allowed(name: str) -> bool:
    return name.startswith("mcp_") or name in ("mcp_tool", "call_mcp_tool")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.agent.tool_gate")
    p.add_argument("--log", required=True)
    args = p.parse_args(argv)
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        payload = {}
    call = payload.get("toolCall") or {}
    name = str(call.get("name") or "")
    ok = allowed(name)
    decision = {"decision": "allow"} if ok else {"decision": "deny", "reason": REASON}
    with open(args.log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": time.time(), "tool": name, "args": call.get("args"), "step": payload.get("stepIdx"),
                             "conversation": payload.get("conversationId"), "decision": decision["decision"]}) + "\n")
    sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
