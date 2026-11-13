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
from mindslice.model.card import sha256_bytes
from mindslice.interfaces.cli import main
from mindslice.interfaces.mcp_server import CLIENTS_FILE, DOCTOR_CLIENT, INSTRUCTIONS, TOOLS, MCPServer, read_clients

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
        code, out, _ = run_cli("-w", w, "--json", "mount", str(slice_root), "--precedence", "50", "--role", "curated")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["alias"], "@kb")

        code, out, _ = run_cli("-w", w, "--json", "write", "api/jwt", "--summary", "JWT TTL is 30 minutes.",
                               "--content-file", "-", "--supersedes", "@kb/api/auth", stdin="- Set TTL to 30m.\n")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["changed"])

        code, out, _ = run_cli("-w", w, "--compact", "search", "token expiration")
        self.assertEqual(json.loads(out)["results"][0]["matched_via_superseded"], ["@kb/api/auth"])
        self.assertEqual(out.count("\n"), 1)

        code, out, _ = run_cli("-w", w, "read", "api/auth")
        self.assertIn("# Jwt", out)
        self.assertIn("redirected from @kb/api/auth", out)

        code, out, _ = run_cli("-w", w, "--json", "read", "api/auth", "--follow", "none")
        self.assertEqual(json.loads(out)["address"], "@kb/api/auth")

        code, out, _ = run_cli("-w", w, "write", "draft", "--summary", "Staged draft.", "--stage")
        code, out, _ = run_cli("-w", w, "diff")
        self.assertIn("+Staged draft.", out)
        code, out, _ = run_cli("-w", w, "--json", "apply")
        self.assertEqual(json.loads(out)["created"], ["@overlay/draft"])

        code, out, _ = run_cli("-w", w, "validate")
        self.assertEqual(code, 0, out)
        code, out, _ = run_cli("-w", w, "--json", "bake", "@out", "--output", str(self.tmp / "out.slice"), "--prefix", "api/")
        self.assertEqual(json.loads(out)["dependencies"], ["@kb"])

        code, out, _ = run_cli("-w", w, "--json", "manifest")
        self.assertEqual([m["alias"] for m in json.loads(out)["mounts"]], ["@overlay", "@kb", "@out"])

    def test_markdown_read_notes_bypassed_replacements(self):
        self.mount_slice("kb", {"a": card_text("A", "Old rule."), "b": card_text("B", "New rule.", supersedes=["a"])},
                         "@kb", 50, "curated")
        self.ws.write("c", summary="Runtime rival.", supersedes=["@kb/a"])
        code, out, _ = run_cli("-w", str(self.root), "read", "@kb/a", "--follow", "curated", "--markdown")
        self.assertEqual(code, 0, out)
        self.assertIn("# B", out)
        self.assertIn("> bypassed_replacements: @overlay/c (supersedes @kb/a)", out)

    def test_errors_go_to_stderr_in_both_formats(self):
        code, out, err = run_cli("-w", str(self.root), "read", "nope")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("error [not_found]: "), err)
        code, out, err = run_cli("-w", str(self.root), "read", "nope", "--json")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(json.loads(err)["code"], "not_found")

    def test_setup_errors_say_what_to_do_next(self):
        missing = self.tmp / "no-workspace"
        code, out, err = run_cli("-w", str(missing), "boot")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("error [workspace_not_found]: ", err)
        self.assertIn(f"`mindslice init {missing}`", err.split("Next:")[1])
        code, _, err = run_cli("-w", str(missing), "boot", "--json")
        self.assertEqual(len(json.loads(err)["details"]["next_steps"]), 2)
        old = os.getcwd()
        os.chdir(self.tmp)
        try:
            code, _, err = run_cli("status")
        finally:
            os.chdir(old)
        self.assertEqual(code, 1)
        self.assertIn("`mindslice -w PATH <command>`", err.split("Next:")[1])
        root = self.mount_slice("kb", {"a": card_text("A", "A.")}, "@kb", 50, "curated")
        other = self.make_slice("other", {"b": card_text("B", "B.")})
        code, _, err = run_cli("-w", str(self.root), "mount", str(other), "--alias", "kb")
        self.assertEqual(code, 1)
        self.assertIn("Next: Mount under another name with `--alias NAME`, or run `mindslice unmount @kb`", err)
        code, _, err = run_cli("-w", str(self.root), "mount", str(root), "--alias", "again")
        self.assertEqual(code, 1)
        self.assertIn("Next: Nothing to do: its cards are available as @kb.", err)

    def test_human_output_by_default_and_json_on_request(self):
        w = str(self.root)
        self.mount_slice("kb", {"api/auth": card_text("Auth", "Token expiration is 15 minutes.")}, "@kb", 50, "curated")
        commands = [("write", "api/jwt", "--summary", "JWT TTL is 30 minutes.", "--supersedes", "@kb/api/auth"),
                    ("search", "token expiration"), ("read", "api/jwt"), ("manifest",), ("validate",),
                    ("write", "draft", "--summary", "Draft.", "--stage"), ("apply", "draft"), ("discard",),
                    ("bake", "@out", "--prefix", "api/", "--dry-run"), ("unmount", "kb")]
        human = {}
        for args in commands:
            with self.subTest(args=args):
                code, out, err = run_cli("-w", w, *args)
                self.assertEqual((code, err), (0, ""), out)
                self.assertFalse(out.lstrip().startswith("{"), out)
                human[args[0]] = human.get(args[0], "") + out
        self.assertIn("Created @overlay/api/jwt", human["write"])
        self.assertIn("Staged create: @overlay/draft", human["write"])
        self.assertIn("1. @overlay/api/jwt — Jwt", human["search"])
        self.assertIn("matched via superseded: @kb/api/auth", human["search"])
        self.assertIn("sha256: " + self.ws.read("api/jwt")["sha256"], human["read"])
        self.assertIn("@kb  1 cards", human["manifest"])
        self.assertIn("OK: ", human["validate"])
        self.assertIn("created: @overlay/draft", human["apply"])
        self.assertIn("Nothing discarded.", human["discard"])
        self.assertIn("Would create @out", human["bake"])
        self.assertIn("Unmounted @kb", human["unmount"])
        for flags in (("--json",), ("--compact",)):
            with self.subTest(flags=flags):
                code, out, _ = run_cli("-w", w, *flags, "search", "jwt")
                self.assertEqual(json.loads(out)["query"], "jwt")
        code, out, _ = run_cli("-w", w, "search", "jwt", "--compact")
        self.assertEqual(out.count("\n"), 1)

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

    def test_argument_errors(self):
        """Argument names that don't fit the schema get a standard invalid_arguments error, not a Python one."""
        err, res = self.tool("write", address="api/jwt", content="x")
        self.assertTrue(err)
        self.assertEqual((res["error"], res["code"]), ("InvalidArgumentsError", "invalid_arguments"))
        self.assertEqual(res["details"]["missing"], ["id"])
        self.assertEqual(res["details"]["unexpected"], ["address"])
        self.assertEqual(res["details"]["hints"], {"address": "id"})
        self.assertIn("did you mean 'id'?", res["message"])
        self.assertIn("Allowed arguments: id, op,", res["message"])
        err, res = self.tool("read")
        self.assertEqual((err, res["code"], res["details"]["missing"]), (True, "invalid_arguments", ["address"]))
        err, res = self.tool("search", queries="token")
        self.assertEqual(res["details"]["hints"], {"queries": "query"})
        err, res = self.tool("write", id="api/new", body="text")
        self.assertEqual((res["details"]["missing"], res["details"]["unexpected"]), ([], ["body"]))
        err, res = self.tool("read", address="api/new")  # nothing was written
        self.assertEqual((err, res["code"]), (True, "not_found"))
        res = self.call("tools/call", {"name": "manifest", "arguments": ["not", "an", "object"]})["result"]
        self.assertTrue(res["isError"])
        self.assertEqual(json.loads(res["content"][0]["text"])["code"], "invalid_arguments")
        err, res = self.tool("search", query="token expiration")  # a valid call is unchanged
        self.assertFalse(err)

    def test_leftover_errors_are_standard(self):
        """A TypeError, KeyError or ValueError raised below the names check comes back as invalid_arguments too."""
        orig = self.server.call_tool

        def boom(name, arguments):
            raise KeyError("x")

        self.server.call_tool = boom
        try:
            err, res = self.tool("manifest")
        finally:
            self.server.call_tool = orig
        self.assertTrue(err)
        self.assertEqual((res["code"], res["details"]["cause"]), ("invalid_arguments", "KeyError"))
        self.assertTrue(res["message"].startswith("manifest: the arguments could not be used"))

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

    def test_manifest_is_a_complete_session_start(self):
        """A client may keep the initialize instructions from the model: manifest returns the same context."""
        self.ws.write("tone", summary="Reply briefly.", load="always", stage=False)
        err, res = self.tool("manifest")
        self.assertFalse(err)
        self.assertEqual(res["instructions"], INSTRUCTIONS)
        self.assertEqual(next(iter(res)), "instructions")  # read before the mount list
        self.assertEqual([c["address"] for c in res["always_loaded"]], ["@overlay/tone"])
        for arguments in ({"include_always": False}, {"offset": 1}):  # later pages and opt-outs stay small
            self.assertNotIn("instructions", self.tool("manifest", **arguments)[1])
        self.assertNotIn("instructions", self.ws.manifest())  # the Python API is unchanged

    def test_search_accepts_limit_for_k(self):
        for i in range(3):
            self.ws.write(f"notes/{i}", summary=f"Token note number {i}.")
        err, res = self.tool("search", query="token", limit=2)
        self.assertFalse(err, res)
        self.assertEqual(len(res["results"]), 2)
        err, res = self.tool("search", query="token", limit=2, k=1)  # both: the schema's name wins, the other is refused
        self.assertEqual((err, res["details"]["unexpected"]), (True, ["limit"]))
        err, res = self.tool("search", query="token", mount="@kb")  # other names are hinted, not accepted
        self.assertEqual((err, res["details"]["hints"]), (True, {"mount": "source"}))
        err, res = self.tool("write", id="x", limit=1)  # write stays strict
        self.assertTrue(err)
        self.assertFalse(self.overlay_file("x").exists())

    def test_connection_record(self):
        """Which app launched the server, and whether it asked for the boot context first."""
        self.assertEqual(read_clients(self.root), {})
        self.tool("search", query="token")  # no initialize (a library caller): nothing recorded
        self.assertEqual(read_clients(self.root), {})
        self.call("initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "some-app", "version": "1.2"}})
        record = read_clients(self.root)["some-app"]
        self.assertEqual((record["version"], record["first_tool"], record["tools_used"]), ("1.2", None, []))
        self.tool("manifest")
        self.tool("search", query="token")
        self.tool("search", query="token again")
        record = read_clients(self.root)["some-app"]
        self.assertEqual((record["first_tool"], record["tools_used"]), ("manifest", ["manifest", "search"]))
        other = MCPServer(self.ws)
        other.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": DOCTOR_CLIENT}}})
        other.handle({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}})
        self.assertEqual(sorted(read_clients(self.root)), ["some-app", "unknown"])  # doctor's own probe is not an app
        (self.root / ".cache" / CLIENTS_FILE).write_text("not json", encoding="utf-8")
        self.assertEqual(read_clients(self.root), {})
        self.assertFalse(self.tool("read", address="@kb/api/auth")[0])  # a broken record never fails a request

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
        proc = self.run_module("--json", "search", "过期")
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
