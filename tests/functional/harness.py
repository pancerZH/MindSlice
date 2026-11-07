"""Journey runner, scripted MCP agent, transcript recording and state fingerprints."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from mindslice import Workspace
from mindslice.mcp_server import MCPServer

# Fields whose values depend on wall-clock time, never on behavior.
VOLATILE_KEYS = frozenset({"mtime_ns", "last_read_at", "updated_at", "started_at"})


class JourneyFailure(AssertionError):
    pass


def expect(condition: Any, message: str) -> None:
    """Assertion that survives ``python -O``."""
    if not condition:
        raise JourneyFailure(message)


def expect_eq(actual: Any, expected: Any, what: str) -> None:
    if actual != expected:
        raise JourneyFailure(f"{what}: expected {expected!r}, got {actual!r}")


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


class Transcript:
    def __init__(self, workspace_root: Path) -> None:
        self.root = workspace_root
        self.entries: list[dict[str, Any]] = []

    def user(self, text: str) -> None:
        self.entries.append({"actor": "user", "text": text})

    def agent(self, tool: str, arguments: dict[str, Any], result: Any, is_error: bool) -> None:
        self.entries.append({"actor": "agent", "tool": tool, "arguments": arguments, "is_error": is_error, "result": result})

    def human(self, action: str, result: Any = None) -> None:
        self.entries.append({"actor": "human", "action": action, "result": result})

    def normalized(self) -> list[Any]:
        return normalize(self.entries, self.root)

    def tail(self, n: int = 6) -> str:
        return "\n".join(json.dumps(e, ensure_ascii=False)[:400] for e in self.normalized()[-n:])


def normalize(value: Any, root: Path) -> Any:
    """Drop wall-clock fields and replace temp paths so two runs compare equal."""
    replacements = [(str(root), "<ws>"), (str(root.parent), "<tmp>")]
    if isinstance(value, dict):
        return {k: normalize(v, root) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, (list, tuple)):
        return [normalize(v, root) for v in value]
    if isinstance(value, str):
        for old, new in replacements:
            value = value.replace(old, new)
        return value
    return value


# ---------------------------------------------------------------------------
# Scripted agent over the real MCP server
# ---------------------------------------------------------------------------


class Agent:
    """A deterministic stand-in for an LLM agent. Every call goes through MCP JSON-RPC."""

    def __init__(self, ws: Workspace, transcript: Transcript, stage_writes: bool = False) -> None:
        self.server = MCPServer(ws, stage_writes=stage_writes)
        self.transcript = transcript
        self._id = 0
        init = self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                         "clientInfo": {"name": "scripted-agent", "version": "1"}})
        expect_eq(init["serverInfo"]["name"], "mindslice", "MCP server name")
        self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.tools = [t["name"] for t in self._rpc("tools/list", {})["tools"]]
        expect_eq(self.tools, ["manifest", "search", "read", "write"], "MCP tool list")

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        self._id += 1
        request = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        # Round-trip through JSON exactly like the stdio transport would.
        response = json.loads(json.dumps(self.server.handle(json.loads(json.dumps(request))), ensure_ascii=False))
        if "error" in response:
            raise JourneyFailure(f"JSON-RPC error for {method}: {response['error']}")
        return response["result"]

    def call(self, tool: str, expect_error: str | None = None, **arguments: Any) -> dict[str, Any]:
        result = self._rpc("tools/call", {"name": tool, "arguments": arguments})
        payload = json.loads(result["content"][0]["text"])
        self.transcript.agent(tool, arguments, payload, result["isError"])
        if expect_error is None and result["isError"]:
            raise JourneyFailure(f"{tool}({arguments}) failed: {payload}")
        if expect_error is not None:
            expect(result["isError"], f"{tool}({arguments}) should have failed with {expect_error}")
            expect_eq(payload.get("code"), expect_error, f"{tool} error code")
        return payload

    def manifest(self, **kw: Any) -> dict[str, Any]:
        return self.call("manifest", **kw)

    def search(self, query: str, **kw: Any) -> dict[str, Any]:
        return self.call("search", query=query, **kw)

    def read(self, address: str, **kw: Any) -> dict[str, Any]:
        return self.call("read", address=address, **kw)

    def write(self, id: str, **kw: Any) -> dict[str, Any]:
        return self.call("write", id=id, **kw)


def addresses(search_result: dict[str, Any]) -> list[str]:
    return [r["address"] for r in search_result["results"]]


# ---------------------------------------------------------------------------
# Journeys
# ---------------------------------------------------------------------------


@dataclass
class Session:
    """One user interaction handled by the (scripted) agent."""

    user: str
    script: Callable[[Agent], None]
    outcome: Callable[[Workspace], None] | None = None
    stage_writes: bool = False


@dataclass
class Human:
    """A human action between sessions (editor save, review, mount...)."""

    action: str
    run: Callable[[Workspace], Any]


@dataclass
class Journey:
    name: str
    setup: Callable[[Path], Workspace]
    steps: list[Session | Human]
    finale: Callable[["JourneyRun"], None]
    probes: tuple[str, ...] = ()


@dataclass
class JourneyRun:
    journey: Journey
    root: Path
    ws: Workspace
    transcript: Transcript
    base_hashes: dict[str, str] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)  # finale results for test assertions
    fingerprint: dict[str, Any] = field(default_factory=dict)

    def human(self, action: str, fn: Callable[[], Any]) -> Any:
        result = fn()
        self.transcript.human(action, result)
        return result


def base_slice_hashes(ws: Workspace) -> dict[str, str]:
    """sha256 of every file in every mounted read-only slice, keyed by absolute path."""
    out: dict[str, str] = {}
    for m in ws.table().mounts:
        for f in sorted(m.root.rglob("*")):
            if f.is_file():
                out[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def check_invariants(run: JourneyRun, where: str) -> None:
    # Base slices are read-only for the engine, mounted or not (re-hash the original files).
    for file, digest in run.base_hashes.items():
        path = Path(file)
        expect(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
               f"[{where}] read-only base slice file changed or vanished: {file}")
    report = run.ws.validate()
    expect(not report["errors"], f"[{where}] validate() errors: {report['errors']}")


def fingerprint(ws: Workspace, probes: tuple[str, ...]) -> dict[str, Any]:
    """Behavior-level summary of a workspace (stable across runs and cache rebuilds)."""
    manifest = ws.manifest(limit=1000)
    return normalize({
        "mounts": [[m["alias"], m["role"], m["precedence"], m["card_count"]] for m in manifest["mounts"]],
        "cards": sorted([r["mount"], r["path"], r["sha256"]] for r in ws.index.all_cards()),
        "probes": {q: [[r["address"], r["coverage"], r["score"]] for r in ws.search(q, k=100)["results"]] for q in probes},
        "staging": [i["id"] for i in ws.diff()["items"]],
    }, ws.root)


def run_journey(journey: Journey, root: Path) -> JourneyRun:
    ws = journey.setup(root)
    run = JourneyRun(journey, root, ws, Transcript(root))
    run.base_hashes = base_slice_hashes(ws)
    try:
        for i, step in enumerate(journey.steps):
            where = f"{journey.name} step {i + 1}"
            if isinstance(step, Session):
                run.transcript.user(step.user)
                step.script(Agent(ws, run.transcript, stage_writes=step.stage_writes))
                check_invariants(run, where)
                if step.outcome is not None:
                    step.outcome(ws)
            else:
                run.transcript.human(step.action, step.run(ws))
        journey.finale(run)
        check_invariants(run, f"{journey.name} finale")
        run.fingerprint = fingerprint(ws, journey.probes)
    except JourneyFailure as exc:
        raise JourneyFailure(f"{exc}\n--- transcript tail ---\n{run.transcript.tail()}") from None
    return run


def restart_with_cold_cache(run: JourneyRun) -> dict[str, Any]:
    """Close, delete .cache (index + lock), reopen: the fingerprint must be rebuilt identically."""
    run.ws.close()
    shutil.rmtree(run.root / ".cache")
    run.ws = Workspace(run.root)
    return fingerprint(run.ws, run.journey.probes)
