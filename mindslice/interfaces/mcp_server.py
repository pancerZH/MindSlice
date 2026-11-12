"""Thin stdio MCP server exposing the four Group A primitives as tools.

Speaks newline-delimited JSON-RPC 2.0 (the MCP stdio transport) using only the
standard library. Tools: ``manifest``, ``search``, ``read``, ``write``.

Run with ``mindslice -w <workspace> mcp`` (add ``--stage-writes`` to force all
agent writes into ``staging/`` for human review via ``diff``/``apply``).

Always-loaded cards (``load = "always"``) reach the agent without a query: rendered into the
``initialize`` instructions, listed by ``manifest``, and, when the set changes mid-session (a slice
mounted, a staged change approved), attached once to the next tool result as
``always_loaded_update``. Agent writes that touch them are always staged for the user's approval:
the agent cannot opt out with ``stage=false``, and ``apply`` is not an agent tool.
"""

from __future__ import annotations

import difflib
import json
import sys
from typing import IO, Any

from .. import __version__
from ..operations.boot import fingerprint, render_markdown
from ..errors import InvalidArgumentsError, MindSliceError
from ..workspace import Workspace

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
            "top-level folders), plus always_loaded: the full always-loaded cards (persona, language, standing "
            "instructions) that apply to the whole session. Call this first to learn what memory exists."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": _int(20, "mounts per page"),
                "offset": _int(0, "pagination offset"),
                "max_folders_per_mount": _int(10, "top-level folders listed per mount"),
                "include_overview": {"type": "boolean", "default": False, "description": "inline each slice's overview.md"},
                "include_always": {"type": "boolean", "default": True, "description": "include always_loaded cards (first page only)"},
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
            "a 1-2 sentence summary plus 5-15 self-contained '- ' bullet statements that keep the concrete values, "
            "names, dates and conditions (search is lexical: a word you leave out can't be found); link related cards "
            "with [[path]]. supersedes and delete act on whole cards, so keep facts that can change on their own on "
            "separate cards. op=create (idempotent if identical), replace (only the fields you pass), append (adds "
            "bullets, skips duplicates; unions tags/aliases/extends/supersedes), delete. supersedes: this card "
            "replaces an outdated one, which stays searchable and forwards its hits here (restate whatever in it is "
            "still true). extends: this card refines, adds an exception or if-then rule to, or depends on another "
            "card as its premise; if that baseline is later superseded or deleted, this card is flagged. A wrong "
            "supersedes hides a card that is still true and extends hides nothing, so when unsure, use extends. "
            "Use delete to forget on request or to remove a wrong card. stage=true buffers the change in staging/ "
            "for human review. Name the id by the durable topic or slot it fills (team/lead, "
            "subscriptions/streaming), never by its current value (team/lead-sarah-chen): ids and links outlive "
            "values. When a write supersedes or deletes a card, the response lists affected_backlinks (cards that "
            "[[link]] to it) and affected_extensions (cards that extend it). Fix them in the same session: rewrite "
            "a card that still states the old value as current or links to a card named after it; rebase an "
            "extension that still holds (replace with extends naming the replacement), else supersede or delete "
            "it. A link to a slot can stay (read() follows supersedes). read_only items are in base slices: "
            "supersede one only if it states the old value as current. load=\"always\" makes a card load into "
            "every session (persona, reply language, standing instructions); any change to the always-loaded context is staged for the user's approval "
            "(requires_approval in the result): tell the user, who approves it with `mindslice apply`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "overlay-relative card path without .md, named by durable topic or slot, "
                       "e.g. \"team/lead\" (not \"team/lead-sarah-chen\"); if the slot's id is taken by the card being "
                       "superseded, qualify it with the date of the change (\"team/lead-2026-11\"), not the new value"},
                "op": {"type": "string", "enum": ["create", "replace", "append", "delete"], "default": "create"},
                "content": {"type": ["string", "array"], "items": {"type": "string"}, "description": "card body (Markdown), or bullet statements for append"},
                "summary": {"type": "string", "description": "1-2 sentence abstract (<= 240 chars) stating the key fact with its concrete value; shown in search previews"},
                "title": {"type": "string", "description": "specific, descriptive title; the most heavily weighted search field"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "facets; searched, and filterable with search(tags=...)"},
                "aliases": {"type": "array", "items": {"type": "string"}, "description": "3-8 search synonyms of 1-4 words: other phrasings, the asker's words, abbreviations, former names, other-language terms (weighted just below the title; also [[alias]] link targets)"},
                "extends": {"type": "array", "items": {"type": "string"}, "description": "baselines this card refines, adds exceptions or if-then rules to, or depends on as a premise (@alias/path); flagged if one is later superseded or deleted"},
                "supersedes": {"type": "array", "items": {"type": "string"}, "description": "outdated cards this one replaces (@alias/path); their search hits forward here"},
                "stage": {"type": "boolean", "description": "true buffers the change in staging/ for human review; "
                          "changes to always-loaded cards are staged whatever you pass"},
                "load": {"type": "string", "enum": ["always", "as-needed"], "description": "\"always\": loaded into "
                         "every session without a query (persona, language, standing instructions); default \"as-needed\""},
                "reason": {"type": "string", "minLength": 1, "description": "Why this change is needed, including the user correction or source when available. Supply this on writes; the engine records history. Never edit .history directly."},
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
    "Supply reason with write() to explain the user correction or evidence for the change. The engine owns "
    ".history/changes.jsonl; never write that log yourself. "
    "Record durable learnings, user corrections and debugging lessons with write() into @overlay: prefer append "
    "to grow an existing card, extends when a card refines, adds an exception or if-then rule to, or depends on "
    "another, supersedes to replace an outdated card (not delete), and delete only to forget on request. Name a "
    "card by the durable topic or slot it fills (team/lead, subscriptions/streaming), never by the value in it "
    "(team/lead-sarah-chen, subscriptions/xelvoria). When a write supersedes or deletes a card, its response lists "
    "affected_backlinks and affected_extensions, the cards that still link to or extend it: update or rebase each "
    "of them in the same session. "
    "Cards marked load=\"always\" are standing context for every session (below, and in manifest's always_loaded; "
    "a tool result's always_loaded_update brings changes to them). When the user states a lasting preference about "
    "how you should behave (reply language, tone, persona), record it with load=\"always\"; such writes are staged "
    "until the user approves them, so tell the user."
)

EMPTY_WORKSPACE_HINT = (
    "# Empty memory workspace\n\n"
    "This MindSlice workspace has no cards or mounted slices yet. If the user is greeting you, testing memory, or "
    "asking how to get started, let them know MindSlice is connected and invite them to seed it in plain language: "
    "(1) how they want you to reply (language, tone, standing rules — record with load=\"always\" and remind them to "
    "approve with `mindslice apply`), (2) their tools, conventions or active projects (record as focused topic cards "
    "in @overlay), or (3) an existing Markdown notes/docs folder or `.slice` to mount via `mindslice mount` (or "
    "distill with the slice-builder skill if you have shell access). If the user is asking a concrete task instead, "
    "handle the task first and record durable preferences or lessons along the way."
)


def format_instructions(snap: dict[str, Any]) -> str:
    """Render MCP server instructions from a ``boot()`` snapshot."""
    text = render_markdown(snap["cards"])
    if text:
        return INSTRUCTIONS + "\n\n" + text
    if snap.get("empty_workspace"):
        return INSTRUCTIONS + "\n\n" + EMPTY_WORKSPACE_HINT + "\n"
    return INSTRUCTIONS


class MCPServer:
    def __init__(self, ws: Workspace, stage_writes: bool = False) -> None:
        self.ws = ws
        self.stage_writes = stage_writes
        self.protocol_version = PROTOCOL_VERSIONS[0]
        # Fingerprints of the always-loaded cards the agent has been given (None: none delivered yet).
        self._boot_seen: dict[str, str] | None = None

    # -- always-loaded cards ----------------------------------------------
    def _boot_cards(self) -> list[dict[str, Any]]:
        return self.ws.boot()["cards"]

    def _mark_seen(self, cards: list[dict[str, Any]]) -> None:
        self._boot_seen = {c["address"]: fingerprint(c) for c in cards}

    def instructions(self) -> str:
        """Server instructions with always-loaded cards (or a cold-start hint when empty) appended."""
        try:
            snap = self.ws.boot()
        except MindSliceError:
            return INSTRUCTIONS
        self._mark_seen(snap["cards"])
        return format_instructions(snap)

    def boot_update(self) -> dict[str, Any] | None:
        """Always-loaded cards added or changed since the agent last saw the set (and those removed)."""
        try:
            cards = self._boot_cards()
        except MindSliceError:
            return None
        seen = self._boot_seen or {}
        current = {c["address"]: fingerprint(c) for c in cards}
        if current == seen:
            self._boot_seen = current
            return None
        self._boot_seen = current
        update: dict[str, Any] = {
            "note": "The always-loaded memory changed (a slice was mounted or the user approved a change). "
                    "These cards apply to the rest of the session.",
            "cards": [c for c in cards if seen.get(c["address"]) != current[c["address"]]],
        }
        removed = [a for a in seen if a not in current]
        if removed:
            update["removed"] = removed
        return update

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
            elif args.get("stage") is False:
                del args["stage"]  # the default: direct, except changes to always-loaded cards (staged for approval)
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
                    "instructions": self.instructions(),
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
        arguments = params.get("arguments")
        try:
            check_arguments(name, {} if arguments is None else arguments)
            payload = self.call_tool(name, arguments or {})
            args = arguments or {}
            if name == "manifest" and args.get("offset", 0) == 0 and args.get("include_always", True):
                self._mark_seen(payload.get("always_loaded", []))
            else:
                update = self.boot_update()
                if update:
                    payload["always_loaded_update"] = update
        except MindSliceError as exc:
            return _tool_result(exc.to_dict(), is_error=True)
        except (TypeError, ValueError, KeyError) as exc:  # raised below the arguments check: still the caller's input
            err = InvalidArgumentsError(f"{name}: the arguments could not be used ({type(exc).__name__}: {exc}).",
                                        tool=name, cause=type(exc).__name__)
            return _tool_result(err.to_dict(), is_error=True)
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


# Names a caller is likely to use for another argument of the same tool (shown as a hint, never accepted).
_ARGUMENT_HINTS = {"write": {"address": "id", "path": "id", "card": "id", "body": "content", "text": "content"},
                   "read": {"id": "address", "path": "address", "card": "address"},
                   "search": {"q": "query", "queries": "query", "text": "query"}}


def check_arguments(name: str, arguments: Any) -> None:
    """The tool call's argument names against the tool's input schema: a missing required argument or one the
    schema doesn't have raises ``InvalidArgumentsError`` naming each, with the allowed names (and a hint where
    a name looks like another argument). Values are not checked here; the tool checks them."""
    schema = next(t["inputSchema"] for t in TOOLS if t["name"] == name)
    if not isinstance(arguments, dict):
        raise InvalidArgumentsError(f"{name}: arguments must be a JSON object, not {type(arguments).__name__}.", tool=name)
    allowed = list(schema.get("properties", {}))
    missing = [k for k in schema.get("required", []) if k not in arguments]
    unexpected = sorted(k for k in arguments if k not in allowed) if schema.get("additionalProperties") is False else []
    if not missing and not unexpected:
        return
    hints = {}
    for k in unexpected:
        guess = _ARGUMENT_HINTS.get(name, {}).get(k) or next(iter(difflib.get_close_matches(k, allowed, n=1, cutoff=0.75)), None)
        if guess:
            hints[k] = guess
    parts = []
    if missing:
        parts.append("missing required argument" + ("s " if len(missing) > 1 else " ") + ", ".join(f"'{k}'" for k in missing))
    if unexpected:
        parts.append("unknown argument" + ("s " if len(unexpected) > 1 else " ") + ", ".join(
            f"'{k}'" + (f" (did you mean '{hints[k]}'?)" if k in hints else "") for k in unexpected))
    raise InvalidArgumentsError(f"{name}: " + "; ".join(parts) + ". Allowed arguments: " + ", ".join(allowed) + ".",
                                tool=name, missing=missing, unexpected=unexpected, allowed=allowed, **({"hints": hints} if hints else {}))


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
