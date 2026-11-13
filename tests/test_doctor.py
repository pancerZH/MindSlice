"""First-use diagnostics distinguish a working engine from an unverified client."""

import json
import subprocess
from unittest.mock import patch

from mindslice.interfaces.doctor import diagnose, probe_mcp

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
        self.assertIn("new conversation", out)
        self.assertIn("    2. Start a new conversation", out)
        self.assertIn(f"mindslice -w {self.root} boot\n", out)  # the real workspace, ready to run

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
        self.assertEqual(self.ws.status()["next_step"]["command"], "bake")
