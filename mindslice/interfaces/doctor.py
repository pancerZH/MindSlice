"""Local diagnostics and a truthful handoff to client-side session verification."""

from __future__ import annotations

import json
import os
import shlex
import sqlite3
import subprocess
import sys

from .. import __version__
from ..errors import MindSliceError
from ..workspace import Workspace
from .mcp_server import format_instructions


def probe_mcp(root):
    """Exercise the real stdio entry point; never execute commands from client configs."""
    command = [sys.executable, "-m", "mindslice", "-w", str(root), "mcp"]
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "mindslice-doctor", "version": __version__}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "manifest", "arguments": {"limit": 1}}},
    ]
    result = subprocess.run(command, input="".join(json.dumps(r) + "\n" for r in requests),
                            capture_output=True, text=True, encoding="utf-8", timeout=10)
    if result.returncode:
        raise ValueError(f"MCP exited with status {result.returncode}: {result.stderr.strip()[:500]}")
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    if any(not isinstance(r, dict) for r in messages):
        raise ValueError("MCP returned an invalid JSON-RPC response")
    replies = {r.get("id"): r for r in messages}
    if any(not isinstance(replies.get(i, {}).get("result"), dict) for i in (1, 2, 3)):
        raise ValueError("MCP did not return successful initialize, tools/list and manifest responses")
    if not replies[1]["result"].get("instructions"):
        raise ValueError("MCP startup instructions are empty")
    names = {t["name"] for t in replies[2]["result"].get("tools", [])}
    if names != {"manifest", "search", "read", "write"} or replies[3]["result"].get("isError"):
        raise ValueError("MCP tools or manifest call failed validation")
    contents = replies[3]["result"].get("content", [])
    manifest = next((json.loads(c["text"]) for c in contents if c.get("type") == "text"), None)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("mounts"), list):
        raise ValueError("MCP manifest response did not contain a mount list")
    return command


def diagnose(root=None):
    checks = []

    def add(name, status, message, action=None, **details):
        checks.append(dict(name=name, status=status, message=message,
                           **({"action": action} if action else {}), **details))

    add("runtime", "pass" if sys.version_info >= (3, 12) else "fail",
        f"MindSlice {__version__}; Python {sys.version.split()[0]}; SQLite {sqlite3.sqlite_version}")
    try:
        with sqlite3.connect(":memory:") as conn:
            conn.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
        add("fts5", "pass", "SQLite FTS5 is available")
    except sqlite3.Error as exc:
        add("fts5", "fail", str(exc), "Use a Python installation with SQLite FTS5 enabled.")

    ws = None
    try:
        ws = Workspace(root, lock_timeout=3) if root else Workspace.discover(lock_timeout=3)
        root = str(ws.root)
        table = ws.table()
        add("workspace", "pass", root)
        missing = [m.alias for m in table.all() if not m.root.is_dir()]
        add("mounts", "fail" if missing else "pass",
            "Missing directories: " + ", ".join(missing) if missing else f"{len(table.mounts)} mounted slice(s)",
            "Restore the directories or unmount the missing slices." if missing else None)
        try:
            validation = ws.validate()
            with ws._reading():
                integrity = [row[0] for row in ws.index.conn.execute("PRAGMA quick_check")]
            if integrity != ["ok"]:
                raise sqlite3.DatabaseError("; ".join(integrity))
            add("index", "pass", "Index synchronized; SQLite integrity check passed")
            add("cards", "fail" if validation["errors"] else ("warn" if validation["warnings"] else "pass"),
                f"{len(validation['errors'])} error(s), {len(validation['warnings'])} warning(s)",
                "Run mindslice -w <workspace> validate for card and reference details."
                if validation["errors"] or validation["warnings"] else None,
                errors=validation["errors"], warnings=validation["warnings"])
        except (MindSliceError, OSError, ValueError, sqlite3.Error) as exc:
            add("index", "fail", str(exc),
                "Run mindslice -w <workspace> validate --rebuild-index. Preserve overlay/, staging/ and .history/.")
        try:
            boot = ws.boot()
            payload = format_instructions(boot)
            add("boot", "pass", f"{boot['total']} standing card(s); {len(payload)} characters in startup payload",
                standing_cards=boot["total"], payload_characters=len(payload))
            if boot.get("pending_approval"):
                add("standing_review", "warn", "Some standing-card changes are still pending, not active",
                    "Run mindslice -w <workspace> review.")
        except (MindSliceError, OSError, ValueError, sqlite3.Error) as exc:
            add("boot", "fail", str(exc), "Resolve workspace errors, then run mindslice -w <workspace> boot.")
        # No workspace lock is held while the subprocess acquires its own lock.
        try:
            command = probe_mcp(ws.root)
            add("mcp", "pass", "Stdio initialize, four tools and manifest succeeded", command=command)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
            add("mcp", "fail", str(exc),
                "Check the Python executable and workspace path in the app's MCP configuration.")
    except (MindSliceError, OSError, ValueError, sqlite3.Error) as exc:
        add("workspace", "fail", str(exc),
            "Use mindslice -w /path/to/workspace doctor, or create a workspace with mindslice init /path/to/workspace.")
    finally:
        if ws is not None:
            ws.close()
    add("client_session", "manual", "Client configuration and model receipt have not been verified",
        "Follow docs/getting-started.md#verify-your-first-session: reconnect the app, start a new conversation, "
        "and verify standing instructions and a memory read; then check the standing instructions are still "
        "present after a context compaction. Local MCP success alone does not prove client loading.")
    return {"ok": not any(c["status"] == "fail" for c in checks), "scope": "local_engine",
            "workspace": str(root) if root else None, "client_verified": False, "checks": checks}


def render(result):
    title = "Local checks passed" if result["ok"] else "Local checks need attention"
    lines = [title + "; client session verification is still required.", ""]
    for check in result["checks"]:
        lines.append(f"[{check['status'].upper()}] {check['name']}: {check['message']}")
        if check.get("action"):
            workspace = result["workspace"] or "/path/to/workspace"
            quoted = subprocess.list2cmdline([workspace]) if os.name == "nt" else shlex.quote(workspace)
            lines.append("  Next: " + check["action"].replace("<workspace>", quoted))
    return "\n".join(lines) + "\n"
