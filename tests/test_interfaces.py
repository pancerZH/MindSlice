"""CLI and MCP server front-ends."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from mindslice import NotFoundError
from mindslice.card import sha256_bytes
from mindslice.cli import main
from mindslice.mcp_server import TOOLS, MCPServer

from .helpers import WorkspaceTestCase, card_text

REPO = Path(__file__).resolve().parents[1]


def run_cli(*args: str, stdin: str | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    old_stdin = sys.stdin
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


class CLITests(WorkspaceTestCase):
    def test_end_to_end(self):
        w = str(self.root)
        slice_root = self.make_slice("kb", {"api/auth": card_text("Auth", "Token expiration is 15 minutes.")}, alias="@kb")
        code, out, _ = run_cli("-w", w, "mount", str(slice_root), "--precedence", "50", "--role", "curated")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["alias"], "@kb")

        code, out, _ = run_cli("-w", w, "write", "api/jwt", "--summary", "JWT TTL is 30 minutes.",
                               "--content-file", "-", "--supersedes", "@kb/api/auth", stdin="- Set TTL to 30m.\n")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["changed"])

        code, out, _ = run_cli("-w", w, "--compact", "search", "token expiration")
        self.assertEqual(json.loads(out)["results"][0]["matched_via_superseded"], ["@kb/api/auth"])
        self.assertEqual(out.count("\n"), 1)

        code, out, _ = run_cli("-w", w, "read", "api/auth", "--markdown")
        self.assertIn("# Jwt", out)
        self.assertIn("redirected from @kb/api/auth", out)

        code, out, _ = run_cli("-w", w, "read", "api/auth", "--follow", "none")
        self.assertEqual(json.loads(out)["address"], "@kb/api/auth")

        code, out, _ = run_cli("-w", w, "write", "draft", "--summary", "Staged draft.", "--stage")
        code, out, _ = run_cli("-w", w, "diff", "--patch")
        self.assertIn("+Staged draft.", out)
        code, out, _ = run_cli("-w", w, "apply")
        self.assertEqual(json.loads(out)["created"], ["@overlay/draft"])

        code, out, _ = run_cli("-w", w, "validate")
        self.assertEqual(code, 0, out)
        code, out, _ = run_cli("-w", w, "pack", str(self.tmp / "out.slice"), "--prefix", "api/")
        self.assertEqual(json.loads(out)["dependencies"], ["@kb"])

        code, out, _ = run_cli("-w", w, "manifest")
        self.assertEqual([m["alias"] for m in json.loads(out)["mounts"]], ["@overlay", "@kb"])

    def test_errors_are_json_on_stderr(self):
        code, _, err = run_cli("-w", str(self.root), "read", "nope")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(err)["code"], "not_found")

    def test_init_and_discovery(self):
        target = self.tmp / "fresh"
        code, out, _ = run_cli("init", str(target))
        self.assertEqual(code, 0)
        self.assertTrue((target / "mounts.toml").is_file())
        self.assertTrue((target / "overlay").is_dir())
        old = os.getcwd()
        os.chdir(target / "overlay")
        try:
            code, out, _ = run_cli("manifest")
        finally:
            os.chdir(old)
        self.assertEqual(code, 0)


class MCPTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.mount_slice("kb", {"api/auth": card_text("Auth", "Token expiration is 15 minutes.")}, "@kb", 50, "curated")
        self.server = MCPServer(self.ws)

    def call(self, method, params=None, msg_id=1):
        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            msg["params"] = params
        return self.server.handle(msg)

    def tool(self, name, **arguments):
        res = self.call("tools/call", {"name": name, "arguments": arguments})["result"]
        return res["isError"], json.loads(res["content"][0]["text"])

    def test_handshake_and_listing(self):
        init = self.call("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t"}})
        self.assertEqual(init["result"]["protocolVersion"], "2025-03-26")
        self.assertIn("tools", init["result"]["capabilities"])
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        names = [t["name"] for t in self.call("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["manifest", "search", "read", "write"])
        self.assertEqual(self.call("bogus")["error"]["code"], -32601)
        self.assertEqual(self.call("ping")["result"], {})

    def test_tools(self):
        err, res = self.tool("manifest")
        self.assertFalse(err)
        self.assertEqual(res["total_mounts"], 2)
        err, res = self.tool("write", id="api/jwt", summary="JWT TTL is 30 minutes.", content=["Set TTL to 30m."],
                             supersedes=["@kb/api/auth"])
        self.assertFalse(err, res)
        err, res = self.tool("search", query="token expiration", follow_supersedes=True)
        self.assertEqual(res["results"][0]["address"], "@overlay/api/jwt")
        err, res = self.tool("read", address="api/auth", follow_supersedes=["curated"])
        self.assertEqual(res["address"], "@kb/api/auth")
        err, res = self.tool("read", address="nope")
        self.assertTrue(err)
        self.assertEqual(res["code"], "not_found")
        err, res = self.tool("write", id="x", bogus=True)
        self.assertTrue(err)

    def test_stage_writes_policy(self):
        server = MCPServer(self.ws, stage_writes=True)
        res = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": "write", "arguments": {"id": "x", "summary": "Staged by policy."}}})
        payload = json.loads(res["result"]["content"][0]["text"])
        self.assertTrue(payload["staged"])
        self.assertEqual([i["id"] for i in self.ws.diff()["items"]], ["x"])

    def test_tool_schemas_are_objects(self):
        for tool in TOOLS:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertTrue(tool["description"])

    def test_stdio_subprocess(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "search", "arguments": {"query": "token"}}},
        ]
        proc = subprocess.run(
            [sys.executable, "-m", "mindslice", "-w", str(self.root), "mcp"],
            input="\n".join(json.dumps(l) for l in lines) + "\nnot json\n",
            capture_output=True, text=True, cwd=REPO, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        responses = [json.loads(l) for l in proc.stdout.splitlines()]
        self.assertEqual([r.get("id") for r in responses], [1, 2, None])
        payload = json.loads(responses[1]["result"]["content"][0]["text"])
        self.assertEqual(payload["results"][0]["address"], "@kb/api/auth")
        self.assertEqual(responses[2]["error"]["code"], -32700)


class NonUtf8ConsoleTests(WorkspaceTestCase):
    """CJK must survive consoles whose default encoding is not UTF-8 (e.g. Windows)."""

    def run_module(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONIOENCODING="ascii", PYTHONPATH=str(REPO))
        return subprocess.run([sys.executable, "-m", "mindslice", "-w", str(self.root), *args],
                              input=stdin.encode("utf-8"), capture_output=True, env=env, timeout=60)

    def test_cli_and_mcp_emit_utf8(self):
        self.ws.write("auth", title="认证流程", summary="令牌过期时间为15分钟。")
        proc = self.run_module("search", "过期")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertEqual(json.loads(proc.stdout.decode("utf-8"))["results"][0]["title"], "认证流程")
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "search", "arguments": {"query": "令牌"}}}
        proc = self.run_module("mcp", stdin=json.dumps(request, ensure_ascii=False) + "\n")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        payload = json.loads(json.loads(proc.stdout.decode("utf-8"))["result"]["content"][0]["text"])
        self.assertEqual(payload["results"][0]["address"], "@overlay/auth")
        proc = self.run_module("write", "笔记", "--content-file", "-", "--summary", "中文摘要。", stdin="- 中文内容\n")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertIn("中文内容", self.ws.read("笔记")["body"])


_WORKER = """
import sys
from mindslice import Workspace
root, wid = sys.argv[1], int(sys.argv[2])
with Workspace(root, lock_timeout=60) as ws:
    for i in range(10):
        if wid % 2 == 0:
            ws.write(f"w{wid}/card{i}", summary=f"Worker {wid} fact {i} about llamas.")
            ws.write("shared/log", op="append", content=f"- entry w{wid} i{i}")
        else:
            ws.search("llamas", k=3)
"""


class ConcurrencyTests(WorkspaceTestCase):
    def run_workers(self, n: int = 4) -> None:
        env = dict(os.environ, PYTHONPATH=str(REPO))
        procs = [
            subprocess.Popen([sys.executable, "-c", _WORKER, str(self.root), str(w)], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for w in range(n)
        ]
        for p in procs:
            _, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err)

    def test_parallel_processes_lose_no_writes(self):
        self.ws.write("shared/log", summary="Shared append log.")
        self.run_workers()
        self.assertEqual(self.ws.search("llamas", k=1)["total_matches"], 20)
        self.assertEqual(self.ws.read("shared/log")["body"].count("- entry"), 20)
        rebuilt = self.ws.validate(rebuild_index=True)["rebuilt_index"]
        self.assertEqual(rebuilt["added"], 21)

    def test_parallel_processes_finish_an_inflight_apply(self):
        self.ws.write("shared/log", summary="Shared append log.")
        self.ws.write("doomed", summary="Card the interrupted batch deletes.")
        self.ws.write("recovered/alpaca", summary="Journaled fact about alpacas.", stage=True)
        self.ws.write("doomed", op="delete", stage=True)
        staging = self.ws.staging
        entries = staging.entries()
        # Crash right after the journal was written: nothing has moved yet.
        staging.write_journal({"version": 1, "overlay_root": str(self.ws.table().overlay.root), "actions": [
            {"op": "delete", "id": "doomed", "base_sha256": entries["doomed"]["base_sha256"]},
            {"op": "move", "id": "recovered/alpaca", "base_sha256": None,
             "sha256": sha256_bytes(staging.file("recovered/alpaca").read_bytes()), "change": "create"},
        ]})
        self.run_workers()  # readers and writers race to find the journal; exactly one may replay it
        self.assertFalse(staging.journal_path.exists())
        self.assertIsNone(self.ws.last_recovery)  # a worker, not this process, finished the batch
        self.assertEqual(self.ws.diff()["items"], [])
        self.assertEqual(self.ws.read("recovered/alpaca")["summary"], "Journaled fact about alpacas.")
        with self.assertRaises(NotFoundError):
            self.ws.read("doomed")
        self.assertEqual(self.ws.search("llamas", k=1)["total_matches"], 20)
        self.assertEqual(self.ws.read("shared/log")["body"].count("- entry"), 20)
        self.assertEqual(self.ws.validate(rebuild_index=True)["rebuilt_index"]["added"], 22)


if __name__ == "__main__":
    unittest.main()
