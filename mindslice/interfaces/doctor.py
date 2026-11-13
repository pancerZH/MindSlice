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
from .mcp_server import DOCTOR_CLIENT, format_instructions, read_clients


# What only the connected app can show. Self-contained: a pip-installed user has no docs checkout to open.
CLIENT_STEPS = [
    "Restart or reconnect the app so it reloads its MCP configuration, open a conversation, and run doctor again: "
    "client_connection should name the app. It should list this server with four tools: manifest, search, read, write.",
    "Give the startup check a phrase the model cannot guess. Save a temporary standing card with words you make up: "
    "mindslice -w <workspace> write setup-check/startup --load always --no-stage "
    "--summary \"The MindSlice startup check phrase is amber maple 47.\" --reason \"Temporary setup check.\"",
    "Start a new conversation (a one-shot, non-interactive session from the shell if the app has one) and send only: "
    "\"What is the MindSlice startup check phrase? Answer from what you were given for this session; do not search "
    "or read memory for it. Say NONE if you do not have it.\" The phrase means standing memory reaches the model; "
    "NONE, or a search or read call, means it does not: fix how the app delivers it, then ask again in another new "
    "conversation.",
    "Remove the card: mindslice -w <workspace> write setup-check/startup --op delete --no-stage "
    "--reason \"Setup check complete.\"",
    "Ask about a fact already saved in memory without repeating it. The answer should come from an actual "
    "search or read call that returns the card.",
    "Let the app compact a long conversation (or trigger compaction if it has a command), then ask for the "
    "standing instructions again. They should still be there.",
    "Go by the app's tool-call or hook log where it has one; the model saying it remembers is not proof.",
]

# Apps that pass MCP server instructions to the model may cut them at a length (a few thousand characters), and
# the standing cards are the end of that text. Above this size, say so.
INSTRUCTIONS_SOFT_LIMIT = 4000


def probe_mcp(root):
    """Exercise the real stdio entry point; never execute commands from client configs."""
    command = [sys.executable, "-m", "mindslice", "-w", str(root), "mcp"]
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": DOCTOR_CLIENT, "version": __version__}}},
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
            long = boot["total"] and len(payload) > INSTRUCTIONS_SOFT_LIMIT
            add("boot", "pass", f"{boot['total']} standing card(s); {len(payload)} characters in startup payload",
                standing_cards=boot["total"], payload_characters=len(payload),
                **({"note": "An app that passes MCP server instructions to the model may cut them at a few thousand "
                            "characters, and the standing cards come last. Do not count on server instructions alone "
                            "for a payload this long: the session-start hook or the manifest rule delivers it whole."}
                   if long else {}))
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
    clients = read_clients(root) if root and ws is not None else {}
    if clients:
        name, last = max(clients.items(), key=lambda item: str(item[1].get("connected_at", "")))
        used = [t for t in last.get("tools_used", []) if isinstance(t, str)]
        others = sorted(n for n in clients if n != name)
        add("client_connection", "pass",
            f"{name}{' ' + last['version'] if isinstance(last.get('version'), str) else ''} started this "
            f"workspace's MCP server at {last.get('connected_at', 'an unknown time')}; "
            + (f"first tool call: {last.get('first_tool')}; tools used: {', '.join(used)}" if used else "no tool call yet")
            + (f"; earlier: {', '.join(others)}" if others else ""),
            note="This shows an app launches the server. It does not show the model received the startup payload.",
            clients=clients)
    elif ws is not None:
        add("client_connection", "pending", "No app has started this workspace's MCP server yet",
            "Restart or reconnect the app, open a conversation and run doctor again. If this stays empty, the app's "
            "MCP entry is not loaded or points at another workspace.")
    add("client_session", "manual", "Client configuration and model receipt have not been verified",
        "Confirm these in the app itself; a local MCP success does not prove the app loads memory into the model.",
        steps=CLIENT_STEPS)
    return {"ok": not any(c["status"] == "fail" for c in checks), "scope": "local_engine",
            "workspace": str(root) if root else None, "client_connected": bool(clients), "client_verified": False,
            "checks": checks}


def render(result):
    title = "Local checks passed" if result["ok"] else "Local checks need attention"
    lines = [title + "; client session verification is still required.", ""]
    workspace = result["workspace"] or "/path/to/workspace"
    quoted = subprocess.list2cmdline([workspace]) if os.name == "nt" else shlex.quote(workspace)
    for check in result["checks"]:
        lines.append(f"[{check['status'].upper()}] {check['name']}: {check['message']}")
        if check.get("action"):
            lines.append("  Next: " + check["action"].replace("<workspace>", quoted))
        if check.get("note"):
            lines.append("  Note: " + check["note"])
        for number, step in enumerate(check.get("steps", []), 1):
            lines.append(f"    {number}. " + step.replace("<workspace>", quoted))
    return "\n".join(lines) + "\n"
