"""First-use diagnostics distinguish a working engine from an unverified client."""

import json
import subprocess
from unittest.mock import patch

from mindslice.interfaces.doctor import diagnose, probe_mcp
from mindslice.interfaces.mcp_server import MCPServer

from .helpers import WorkspaceTestCase, card_text
from .test_interfaces import run_cli


class DoctorTests(WorkspaceTestCase):
    def test_real_stdio_probe_empty_and_seeded_workspace_without_creating_memory(self):
        result = diagnose(self.root)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["client_verified"])
        checks = {item["name"]: item for item in result["checks"]}
        self.assertEqual(checks["mcp"]["status"], "pass")
        self.assertEqual(checks["client_session"]["status"], "manual")
        steps = checks["client_session"]["steps"]
        self.assertTrue(any("compact" in step for step in steps), steps)
        # The report has to stand on its own: no pointer to a doc or skill the reader may not have.
        report = json.dumps(result)
        self.assertNotIn(".md", report)
        self.assertNotIn("docs/", report)
        self.assertEqual(checks["boot"]["standing_cards"], 0)
        self.assertEqual(list((self.root / "overlay").rglob("*.md")), [])
        self.assertEqual(self.ws.history.events(), [])
        self.ws.write("tone", summary="Use concise replies.", load="always")
        result = diagnose(self.root)
        checks = {item["name"]: item for item in result["checks"]}
        self.assertEqual(checks["standing_review"]["status"], "warn")
        self.assertEqual(checks["boot"]["standing_cards"], 0)
        self.ws.apply(["tone"])
        checks = {item["name"]: item for item in diagnose(self.root)["checks"]}
        self.assertEqual(checks["boot"]["standing_cards"], 1)

    def test_missing_workspace_is_actionable_and_does_not_create_it(self):
        missing = self.tmp / "missing"
        code, out, err = run_cli("-w", str(missing), "doctor", "--json")
        self.assertEqual((code, err), (1, ""))
        result = json.loads(out)
        self.assertFalse(result["ok"])
        self.assertIn("mindslice init", next(c for c in result["checks"] if c["name"] == "workspace")["action"])
        self.assertFalse(missing.exists())

    def test_malformed_mount_table_is_a_report_not_an_uncaught_exception(self):
        (self.root / "mounts.toml").write_text("[[broken")
        result = diagnose(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(c["name"] == "workspace" and c["status"] == "fail" for c in result["checks"]))

    def test_missing_mount_and_invalid_card_report_failures(self):
        root = self.mount_slice("kb", {"note": card_text("Note", "Memory.")}, "@kb", 40, "curated")
        root.rename(root.with_name("moved"))
        result = diagnose(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(next(c for c in result["checks"] if c["name"] == "mounts")["status"], "fail")
        self.put_overlay("invalid", "+++\ntitle = [\n+++\nBroken card.")
        result = diagnose(self.root)
        self.assertTrue(next(c for c in result["checks"] if c["name"] == "cards")["errors"])

    def test_mcp_timeout_and_error_are_reported_without_claiming_client_success(self):
        for failure in (subprocess.TimeoutExpired("mcp", 10), ValueError("MCP failed")):
            with patch("mindslice.interfaces.doctor.probe_mcp", side_effect=failure):
                result = diagnose(self.root)
            self.assertFalse(result["ok"])
            self.assertFalse(result["client_verified"])
            self.assertEqual(next(c for c in result["checks"] if c["name"] == "mcp")["status"], "fail")

    def test_mcp_process_failure_and_protocol_error_are_rejected(self):
        cases = [subprocess.CompletedProcess([], 1, "", "cannot start"),
                 subprocess.CompletedProcess([], 0, '{"id":1,"error":{"message":"failed"}}\n', "")]
        for result in cases:
            with patch("mindslice.interfaces.doctor.subprocess.run", return_value=result):
                with self.assertRaises(ValueError):
                    probe_mcp(self.root)

    def test_human_output_and_environment_workspace(self):
        with patch.dict("os.environ", {"MINDSLICE_WORKSPACE": str(self.root)}):
            code, out, err = run_cli("doctor")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Local checks passed", out)
        self.assertIn("[MANUAL] client_session", out)
        self.assertIn("[PENDING] client_connection", out)
        self.assertIn("    3. Start a new conversation", out)
        self.assertIn("startup check phrase", out)
        # The real workspace, ready to run: a phrase to plant, and its removal.
        self.assertIn(f"    2. Give the startup check a phrase the model cannot guess. Save a temporary standing card "
                      f"with words you make up: mindslice -w {self.root} write setup-check/startup --load always", out)
        self.assertIn(f"mindslice -w {self.root} write setup-check/startup --op delete --no-stage", out)

    def test_the_startup_check_commands_work_as_printed(self):
        """Step 2 plants a standing card without a review; step 4 removes it again."""
        w = str(self.root)
        code, _, err = run_cli("-w", w, "write", "setup-check/startup", "--load", "always", "--no-stage",
                               "--summary", "The MindSlice startup check phrase is amber maple 47.",
                               "--reason", "Temporary setup check.")
        self.assertEqual((code, err), (0, ""))
        code, out, _ = run_cli("-w", w, "boot")
        self.assertIn("amber maple 47", out)
        code, _, err = run_cli("-w", w, "write", "setup-check/startup", "--op", "delete", "--no-stage",
                               "--reason", "Setup check complete.")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.ws.boot()["total"], 0)
        self.assertEqual(self.ws.status()["pending_review"]["summary"]["total"], 0)

    def test_client_connection_is_reported_from_the_server_record(self):
        result = diagnose(self.root)  # doctor's own handshake is not an app connecting
        checks = {item["name"]: item for item in result["checks"]}
        self.assertEqual(checks["client_connection"]["status"], "pending")
        self.assertFalse(result["client_connected"])
        self.assertTrue(result["ok"])
        server = MCPServer(self.ws)
        server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"clientInfo": {"name": "some-app", "version": "2.0"}}})
        server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "manifest", "arguments": {}}})
        result = diagnose(self.root)
        check = next(c for c in result["checks"] if c["name"] == "client_connection")
        self.assertEqual(check["status"], "pass")
        self.assertIn("some-app 2.0", check["message"])
        self.assertIn("first tool call: manifest", check["message"])
        self.assertTrue(result["client_connected"])
        self.assertFalse(result["client_verified"])  # a connection is not the model receiving the payload
        self.assertEqual(result["checks"][-1]["name"], "client_session")

    def test_long_startup_payload_is_noted(self):
        self.ws.write("short", summary="Reply briefly.", load="always", stage=False)
        self.assertNotIn("note", next(c for c in diagnose(self.root)["checks"] if c["name"] == "boot"))
        self.ws.write("long", summary="A long standing rule.", content=["rule " + "x" * 80 for _ in range(12)],
                      load="always", stage=False)
        check = next(c for c in diagnose(self.root)["checks"] if c["name"] == "boot")
        self.assertEqual(check["status"], "pass")
        self.assertIn("cut them", check["note"])
        code, out, _ = run_cli("-w", str(self.root), "doctor")
        self.assertIn("  Note: An app that passes MCP server instructions", out)

    def test_status_explains_saved_pending_and_unassigned_with_next_action(self):
        self.ws.write("saved", summary="Already persisted.")
        self.ws.write("pending", summary="Not yet active.", stage=True)
        result = self.ws.status()
        self.assertEqual(result["memory_state"], {"saved_overlay_cards": 1, "mounted_cards": 0,
                         "pending_changes": 1, "unassigned_cards": 1})
        self.assertEqual(result["next_step"]["command"], "review")
        code, out, _ = run_cli("-w", str(self.root), "status")
        self.assertEqual(code, 0)
        self.assertIn("already saved", out)
        self.assertIn("not an error", out)
        self.ws.discard(["pending"])
        result = self.ws.status()
        self.assertEqual(result["next_step"]["command"], "bake")
        self.assertTrue(result["clean"])  # saved and live; nothing waits for the user

    def test_a_standing_overlay_card_is_not_unfinished_work(self):
        """A load="always" card normally lives in the overlay: status is clean and does not keep suggesting bake."""
        self.ws.write("rules/tone", summary="Reply briefly.", load="always", stage=False)
        result = self.ws.status()
        self.assertEqual(result["unassigned_overlay_cards"], [dict(result["unassigned_overlay_cards"][0], standing=True)])
        self.assertTrue(result["clean"])
        self.assertEqual(result["next_step"]["command"], "doctor")
        code, out, _ = run_cli("-w", str(self.root), "status")
        self.assertIn("@overlay/rules/tone [standing]", out)
        self.assertIn("No pending review or unbaked slice changes.", out)
        self.ws.write("notes/topic", summary="An ordinary card.")
        result = self.ws.status()
        self.assertEqual((result["clean"], result["next_step"]["command"]), (True, "bake"))
        self.assertNotIn("standing", result["unassigned_overlay_cards"][0])
        self.ws.write("rules/draft", summary="Not active yet.", stage=True)
        self.assertFalse(self.ws.status()["clean"])
