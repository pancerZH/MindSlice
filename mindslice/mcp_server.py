"""Thin stdio MCP server exposing the four Group A primitives as tools.

Speaks newline-delimited JSON-RPC 2.0 (the MCP stdio transport) using only the
standard library. Tools: ``manifest``, ``search``, ``read``, ``write``.

Run with ``mindslice -w <workspace> mcp`` (add ``--stage-writes`` to force all
agent writes into ``staging/`` for human review via ``diff``/``apply``).
"""

from __future__ import annotations

import json
import sys
from typing import IO, Any

from . import __version__
from .errors import MindSliceError
from .workspace import Workspace

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

_FOLLOW_SCHEMA = {
    "type": ["boolean", "array"],
    "items": {"type": "string"},
    "description": "true = follow every supersedes edge (default); false = never; or an allowlist of mount roles / @aliases "
    "whose replacements are trusted (e.g. [\"curated\"]). Untrusted replacements are still reported.",
}


def _int(default: int, desc: str) -> dict[str, Any]:
    return {"type": "integer", "minimum": 0, "default": default, "description": desc}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "manifest",
        "description": (
            "Boot context: list mounted memory slices (alias, role, precedence, card counts, 160-char description, "
            "top-level folders). Call this first to learn what memory exists."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": _int(20, "mounts per page"),
                "offset": _int(0, "pagination offset"),
                "max_folders_per_mount": _int(10, "top-level folders listed per mount"),
                "include_overview": {"type": "boolean", "default": False, "description": "inline each slice's overview.md"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "search",
        "description": (
            "Associative lexical search across all mounted slices (any language, including unspaced Chinese/Japanese/"
            "Korean), ranked by BM25 score. Each card preview also reports coverage, the share of the query it matched. Returns card "
            "previews (address, role, coverage, score, title, 240-char summary, 1-hop [[wikilink]] neighbors). Hits on "
            "superseded cards are redirected to their replacement (see matched_via_superseded; bypassed_replacements "
            "lists replacements your follow_supersedes policy did not trust). A preview whose "
            "extends chain changed says so: baseline_superseded_by (a baseline, at any depth, was replaced) or "
            "missing_baselines (one was deleted); read it before relying on it. Use read() on an "
            "address for full content. Search is lexical: unmatched_terms lists query words no card contains. When "
            "results are empty or weak, rephrase those words (fix a typo, try a synonym or the other language) or "
            "reuse the vocabulary of the cards you did find."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "free text; words are OR-ed and ranked by BM25 (word* = prefix); CJK needs no spaces"},
                "source": {"type": ["string", "array"], "items": {"type": "string"}, "description": "restrict to mount alias(es), e.g. \"@project\""},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "cards must carry all of these tags"},
                "k": _int(10, "max results"),
                "offset": _int(0, "pagination offset"),
                "max_neighbors": _int(3, "wikilink neighbors per preview"),
                "follow_supersedes": _FOLLOW_SCHEMA,
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read",
        "description": (
            "Read one card by address: '@alias/path' (exact mount) or 'path' (highest-precedence mount wins; other "
            "same-path cards are listed in shadows). Follows supersedes to the replacement (redirected_from; untrusted "
            "replacements are listed in superseded_by_untrusted and bypassed_replacements, not followed), composes "
            "extends baselines/extensions, and returns sha256 (pass it as write.if_match), links and backlinks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "e.g. \"@project/api/auth-flow\" or \"api/auth-flow\""},
                "follow_supersedes": _FOLLOW_SCHEMA,
                "max_backlinks": _int(10, "backlinks per page"),
                "backlinks_offset": _int(0, "backlinks pagination offset"),
                "max_extensions": _int(5, "extensions per page"),
                "extensions_offset": _int(0, "extensions pagination offset"),
            },
            "required": ["address"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write",
        "description": (
            "Record memory in the writable @overlay layer (base slices are read-only). One focused sub-topic per card: "
            "a 1-2 sentence summary plus 5-15 atomic '- ' bullet statements; link related cards with [[path]]. "
            "op=create (idempotent if identical), replace (only the fields you pass), append (adds bullets, skips "
            "duplicates; unions tags/aliases/extends/supersedes), delete. Use extends to add exceptions to a base card, "
            "supersedes to replace one. stage=true buffers the change in staging/ for human review."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "overlay-relative card path without .md, e.g. \"api/auth-edge-cases\""},
                "op": {"type": "string", "enum": ["create", "replace", "append", "delete"], "default": "create"},
                "content": {"type": ["string", "array"], "items": {"type": "string"}, "description": "card body (Markdown), or bullet statements for append"},
                "summary": {"type": "string", "description": "1-2 sentence abstract (<= 240 chars)"},
                "title": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "extends": {"type": "array", "items": {"type": "string"}, "description": "cards this one adds exceptions/details to (@alias/path)"},
                "supersedes": {"type": "array", "items": {"type": "string"}, "description": "cards this one replaces (@alias/path)"},
                "stage": {"type": "boolean", "default": False},
                "if_match": {"type": "string", "description": "sha256 from read(); rejects the write if the card changed"},
            },
            "required": ["id"],
            "additionalProperties": False,
        },
    },
]

INSTRUCTIONS = (
    "MindSlice is your long-term memory. Start with manifest() to see the mounted slices, use search() to find "
    "relevant cards, and read() an address for full content (it composes extensions and follows replacements). "
    "Record durable learnings, user corrections and debugging lessons with write() into @overlay: prefer append "
    "to grow an existing card, extends to add exceptions to a base card, and supersedes to replace outdated ones."
)


class MCPServer:
    def __init__(self, ws: Workspace, stage_writes: bool = False) -> None:
        self.ws = ws
        self.stage_writes = stage_writes
        self.protocol_version = PROTOCOL_VERSIONS[0]

    # -- tool execution ---------------------------------------------------
    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        args = dict(arguments or {})
        if name == "manifest":
            return self.ws.manifest(**args)
        if name == "search":
            return self.ws.search(args.pop("query"), **args)
        if name == "read":
            return self.ws.read(args.pop("address"), **args)
        if name == "write":
            if self.stage_writes:
                args["stage"] = True
            return self.ws.write(args.pop("id"), **args)
        raise KeyError(name)

    # -- JSON-RPC ---------------------------------------------------------
    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, -32600, "invalid request")
        method = message.get("method")
        msg_id = message.get("id")
        is_notification = "id" not in message
        params = message.get("params") or {}
        try:
            if method == "initialize":
                requested = params.get("protocolVersion")
                self.protocol_version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
                result = {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "mindslice", "version": __version__},
                    "instructions": INSTRUCTIONS,
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self._tools_call(params)
            elif isinstance(method, str) and method.startswith("notifications/"):
                return None
            else:
                return None if is_notification else _error(msg_id, -32601, f"method not found: {method}")
        except Exception as exc:  # pragma: no cover - defensive
            return None if is_notification else _error(msg_id, -32603, f"internal error: {exc}")
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if name not in {t["name"] for t in TOOLS}:
            return _tool_result({"error": "UnknownTool", "message": f"unknown tool {name!r}"}, is_error=True)
        try:
            payload = self.call_tool(name, params.get("arguments") or {})
        except MindSliceError as exc:
            return _tool_result(exc.to_dict(), is_error=True)
        except (TypeError, ValueError, KeyError) as exc:
            return _tool_result({"error": type(exc).__name__, "message": str(exc)}, is_error=True)
        return _tool_result(payload)

    def serve(self, stdin: IO[str], stdout: IO[str]) -> None:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                response: Any = _error(None, -32700, "parse error")
            else:
                if isinstance(message, list):  # JSON-RPC batch (2025-03-26)
                    response = [r for r in (self.handle(m) for m in message) if r is not None] or None
                else:
                    response = self.handle(message)
            if response is not None:
                stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                stdout.flush()


def _tool_result(payload: dict[str, Any], is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "isError": is_error}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def ensure_utf8_stdio() -> None:
    """Pin stdio to UTF-8 (the MCP stdio transport requires it) whatever the console locale is.

    Without this, CJK text crashes on Windows consoles or under ``PYTHONIOENCODING=ascii``.
    Must run before anything is read from stdin.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):  # already consumed or detached; leave it alone
            pass


def serve(ws: Workspace, stage_writes: bool = False, stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> None:
    if stdin is None or stdout is None:
        ensure_utf8_stdio()
    MCPServer(ws, stage_writes).serve(stdin or sys.stdin, stdout or sys.stdout)


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="MindSlice MCP server (stdio)")
    parser.add_argument("workspace")
    parser.add_argument("--stage-writes", action="store_true")
    ns = parser.parse_args()
    with Workspace(ns.workspace) as workspace:
        serve(workspace, ns.stage_writes)
