"""Persistent reasons, lifecycle linkage, and crash recovery without a history database."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

from mindslice import ApplyConflictError, HistoryError, InvalidArgumentsError, NotFoundError, Workspace
from mindslice.card import parse_card
from mindslice.mcp_server import MCPServer

from .helpers import WorkspaceTestCase, card_text
from .test_interfaces import run_cli


class HistoryTests(WorkspaceTestCase):
    def events(self):
        return self.ws.history.events()

    def test_direct_writes_record_reasons_without_changing_card_content(self):
        first = self.ws.write("python/style", summary="Use ruff.", reason="User selected ruff.")
        second = self.ws.write("python/style", op="append", content="- Run it in CI.", reason="CI policy updated.")
        events = self.events()
        self.assertEqual([e["event"] for e in events], ["applied", "applied"])
        self.assertEqual([e["change_id"] for e in events], [first["change_id"], second["change_id"]])
        self.assertEqual(events[1]["before_sha256"], events[0]["after_sha256"])
        self.assertEqual(events[1]["after_sha256"], second["sha256"])
        self.assertEqual(events[0]["reason"], "User selected ruff.")
        self.assertEqual(events[0]["address"], "@overlay/python/style")
        self.assertIn("timestamp", events[0])
        self.assertNotIn("reason", parse_card(self.overlay_file("python/style").read_text()).frontmatter)
        self.assertNotIn("User selected ruff", self.overlay_file("python/style").read_text())
        self.assertNotIn("content", events[0])
        self.assertEqual(self.ws.search("selected")["total_matches"], 0)
        [item] = self.ws.diff("overlay")["items"]
        self.assertEqual(item["change_ids"], [first["change_id"], second["change_id"]])
        self.assertEqual([c["reason"] for c in item["changes"]], ["User selected ruff.", "CI policy updated."])

    def test_staged_chain_survives_apply_and_cache_rebuild(self):
        first = self.ws.write("note", summary="Draft.", stage=True, reason="First proposal.")
        second = self.ws.write("note", op="replace", summary="Approved wording.", stage=True, reason="Clarify the wording.")
        ids = [first["change_id"], second["change_id"]]
        self.assertEqual([e["event"] for e in self.events()], ["proposed", "proposed"])
        self.assertEqual(self.ws.staging.entries()["note"]["change_ids"], ids)
        self.assertEqual([c["reason"] for c in self.ws.diff()["items"][0]["changes"]],
                         ["First proposal.", "Clarify the wording."])
        self.assertEqual(self.ws.status()["pending_review"]["files"][0]["change_ids"], ids)
        with self.assertRaises(NotFoundError):
            self.ws.read("note")
        self.ws.apply()
        self.assertEqual([e["change_id"] for e in self.events() if e["event"] == "applied"], ids)
        self.assertEqual(self.ws.diff("overlay")["items"][0]["change_ids"], ids)
        history = self.ws.history.path.read_bytes()
        self.ws.close()
        shutil.rmtree(self.root / ".cache")
        self.ws = Workspace(self.root)
        self.assertEqual(self.ws.read("note")["summary"], "Approved wording.")
        self.assertEqual(self.ws.history.path.read_bytes(), history)
        self.assertEqual(self.ws.diff("overlay")["items"][0]["change_ids"], ids)

    def test_discard_keeps_reasons_and_staged_create_cancellation_is_recorded(self):
        proposal = self.ws.write("draft", summary="Never applied.", stage=True, reason="Try an alternative.")
        self.ws.discard()
        events = self.events()
        self.assertEqual([e["event"] for e in events], ["proposed", "discarded"])
        self.assertEqual(events[-1]["change_id"], proposal["change_id"])
        self.assertEqual(events[0]["reason"], "Try an alternative.")
        first = self.ws.write("cancel", summary="Temporary proposal.", stage=True, reason="Consider this.")
        deleted = self.ws.write("cancel", op="delete", stage=True, reason="User withdrew the proposal.")
        discarded = [e["change_id"] for e in self.events() if e["event"] == "discarded"]
        self.assertIn(first["change_id"], discarded)
        self.assertIn(deleted["change_id"], discarded)
        self.assertEqual(self.ws.diff()["items"], [])
        self.assertFalse(self.overlay_file("cancel").exists())

    def test_delete_and_reasonless_writes_are_logged_but_noops_are_not(self):
        self.ws.write("note", summary="Original.")
        self.ws.write("note", summary="Original.", reason="Retry.")
        self.assertEqual(len(self.events()), 1)
        self.assertIsNone(self.events()[0]["reason"])
        self.ws.write("note", op="delete", reason="User asked to forget it.")
        self.ws.write("note", op="delete", reason="Retry deletion.")
        self.assertEqual(len(self.events()), 2)
        self.assertIsNone(self.events()[-1]["after_sha256"])
        self.assertEqual(self.events()[-1]["reason"], "User asked to forget it.")

    def test_failed_writes_and_apply_conflicts_do_not_claim_success(self):
        for reason in ("", "  ", 123, ["reason"]):
            with self.subTest(reason=reason), self.assertRaises(InvalidArgumentsError):
                self.ws.write("bad", summary="Invalid reason.", reason=reason)
        self.assertFalse(self.ws.history.path.exists())
        self.ws.write("note", summary="Original.")
        proposal = self.ws.write("note", op="replace", summary="Draft.", stage=True, reason="Proposed correction.")
        self.put_overlay("note", card_text("Note", "Concurrent external change."))
        before = self.ws.history.path.read_bytes()
        with self.assertRaises(ApplyConflictError):
            self.ws.apply()
        self.assertEqual(self.ws.history.path.read_bytes(), before)
        self.assertEqual(self.ws.diff()["items"][0]["change_ids"], [proposal["change_id"]])

    def test_external_edits_do_not_inherit_stale_reason_chains(self):
        first = self.ws.write("note", summary="Original.", reason="Old reason.")
        self.put_overlay("note", card_text("Note", "External content."))
        self.assertNotIn("changes", self.ws.diff("overlay")["items"][0])
        second = self.ws.write("note", op="append", content="- New fact.", reason="New reason.")
        ids = self.ws.diff("overlay")["items"][0]["change_ids"]
        self.assertEqual(ids, [second["change_id"]])
        self.assertNotIn(first["change_id"], ids)

    def test_bake_records_version_pointer_and_retained_reasons_without_exporting_log(self):
        initial = self.ws.write("python/style", summary="Use ruff.", reason="Team choice.")
        self.ws.write("diary", summary="See [[python/style]].", reason="Keep a pointer.")
        before = self.ws.history.path.read_bytes()
        self.ws.bake("python", prefix="python/", dry_run=True)
        self.assertEqual(self.ws.history.path.read_bytes(), before)
        output = self.tmp / "python.zip"
        result = self.ws.bake("python", output, prefix="python/")
        baked = next(e for e in self.events() if e["event_id"] == result["history_event_id"])
        self.assertEqual(baked["event"], "baked")
        self.assertEqual(baked["change_ids"], [initial["change_id"]])
        self.assertEqual((baked["path"], baked["version"], baked["alias"]),
                         (result["path"], "0.1.0", "@python"))
        self.assertEqual(baked["cards"][0]["target"], "@python/python/style")
        self.assertEqual(baked["cards"][0]["before_sha256"], initial["sha256"])
        self.assertFalse((Path(result["path"]) / ".history").exists())
        with zipfile.ZipFile(output) as archive:
            self.assertFalse(any(".history" in name for name in archive.namelist()))
        self.assertEqual(self.ws.diff("overlay")["items"][0]["changes"][-1]["op"], "rebase")
        self.ws.write("python/style", summary="Use ruff and mypy.", reason="Add type checking.")
        updated = self.ws.bake("python")
        self.assertEqual(self.events()[-1]["previous_path"], result["path"])
        self.assertEqual(self.events()[-1]["path"], updated["path"])
        self.assertEqual(self.events()[-1]["version"], "0.1.1")

    def test_cli_and_mcp_accept_only_reason_and_show_review_metadata(self):
        code, out, err = run_cli("-w", str(self.root), "write", "note", "--summary", "Proposed text.",
                                "--stage", "--reason", "User corrected the date.")
        self.assertEqual((code, err), (0, ""))
        id = json.loads(out)["change_id"]
        code, out, err = run_cli("-w", str(self.root), "diff")
        self.assertEqual(code, 0)
        self.assertIn("+Proposed text.", out)
        self.assertNotIn("User corrected", out)
        self.assertIn("User corrected the date.", err)
        code, out, _ = run_cli("-w", str(self.root), "status")
        self.assertIn("User corrected the date.", out)
        server = MCPServer(self.ws)
        def call(arguments):
            result = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                    "params": {"name": "write", "arguments": arguments}})["result"]
            return result["isError"], json.loads(result["content"][0]["text"])
        error, result = call({"id": "agent", "summary": "Agent content.", "reason": "Documented project rule."})
        self.assertFalse(error, result)
        self.assertEqual(result["reason"], "Documented project rule.")
        error, result = call({"id": "fake", "summary": "Fake.", "reason": "Try.", "change_id": id})
        self.assertTrue(error)
        self.assertEqual(result["code"], "invalid_arguments")
        self.assertFalse(self.overlay_file("fake").exists())


class HistoryRecoveryTests(WorkspaceTestCase):
    def restart(self):
        self.ws.close()
        self.ws = Workspace(self.root)

    def test_direct_write_recovers_if_event_append_failed(self):
        with patch.object(self.ws.history, "append", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.ws.write("note", summary="Durable content.", reason="Durable reason.")
        self.assertTrue(self.overlay_file("note").exists())
        self.assertTrue(self.ws.history.has_journal())
        self.restart()
        self.assertEqual(self.ws.read("note")["summary"], "Durable content.")
        self.assertEqual(self.ws.history.events()[0]["reason"], "Durable reason.")
        self.assertFalse(self.ws.history.has_journal())
        self.restart()
        self.ws.status()
        self.assertEqual(len(self.ws.history.events()), 1)

    def test_recovery_after_append_does_not_duplicate_events(self):
        from mindslice.history import unlink_if_exists as unlink
        def stop(path):
            if path == self.ws.history.journal_path:
                raise OSError("crashed after append")
            return unlink(path)
        with patch("mindslice.history.unlink_if_exists", side_effect=stop):
            with self.assertRaises(OSError):
                self.ws.write("note", summary="Once.", reason="Exactly one event.")
        self.assertEqual(len(self.ws.history.events()), 1)
        self.restart()
        self.ws.read("note")
        self.assertEqual(len(self.ws.history.events()), 1)

    def test_torn_last_log_line_is_recovered_from_journal(self):
        self.ws.write("base", summary="Existing event.")
        with patch.object(self.ws.history, "append", side_effect=OSError("interrupted append")):
            with self.assertRaises(OSError):
                self.ws.write("next", summary="New event.", reason="Recover this.")
        with self.ws.history.path.open("ab") as stream:
            stream.write(b'{"event_id":"partial')
        self.restart()
        self.ws.read("next")
        events = self.ws.history.events()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1]["reason"], "Recover this.")
        for line in self.ws.history.path.read_text().splitlines():
            json.loads(line)

    def test_external_edit_during_history_recovery_is_preserved(self):
        with patch.object(self.ws.history, "append", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                self.ws.write("note", summary="Engine content.")
        external = card_text("Note", "User edited after the interruption.")
        self.overlay_file("note").write_text(external)
        self.restart()
        with self.assertRaises(HistoryError):
            self.ws.status()
        self.assertEqual(self.overlay_file("note").read_text(), external)
        self.assertTrue(self.ws.history.has_journal())

    def test_corrupt_complete_log_line_blocks_writes_without_losing_data(self):
        self.ws.write("note", summary="Original.")
        before = self.overlay_file("note").read_bytes()
        with self.ws.history.path.open("ab") as stream:
            stream.write(b'not json\n')
        with self.assertRaises(HistoryError):
            self.ws.write("note", op="replace", summary="Must not be written.")
        self.assertEqual(self.overlay_file("note").read_bytes(), before)

    def test_apply_log_failure_is_replayed_with_the_original_change_ids(self):
        proposal = self.ws.write("note", summary="Approved content.", stage=True, reason="User request.")
        with patch.object(self.ws.history, "append", side_effect=OSError("log failure")):
            with self.assertRaises(OSError):
                self.ws.apply()
        self.assertTrue(self.ws.staging.has_journal())
        self.restart()
        self.assertEqual(self.ws.read("note")["summary"], "Approved content.")
        events = self.ws.history.events()
        self.assertEqual([e["event"] for e in events], ["proposed", "applied"])
        self.assertEqual(events[-1]["change_id"], proposal["change_id"])
        self.assertFalse(self.ws.staging.has_journal())

    def test_discard_log_failure_recovers_after_staging_was_removed(self):
        proposal = self.ws.write("note", summary="Rejected.", stage=True, reason="Alternative idea.")
        with patch.object(self.ws.history, "append", side_effect=OSError("log failure")):
            with self.assertRaises(OSError):
                self.ws.discard()
        self.restart()
        self.assertEqual(self.ws.diff()["items"], [])
        events = self.ws.history.events()
        self.assertEqual(events[-1]["event"], "discarded")
        self.assertEqual(events[-1]["change_id"], proposal["change_id"])

    def test_bake_recovers_mount_retirement_and_version_event(self):
        initial = self.ws.write("python/style", summary="Use ruff.", reason="Team standard.")
        self.ws.write("diary", summary="Read [[python/style]].")
        with patch.object(self.ws.history, "append", side_effect=OSError("log failure")):
            with self.assertRaises(OSError):
                self.ws.bake("python", prefix="python/")
        self.restart()
        self.assertEqual(self.ws.read("@python/python/style")["summary"], "Use ruff.")
        self.assertFalse(self.overlay_file("python/style").exists())
        self.assertIn("[[@python/python/style]]", self.overlay_file("diary").read_text())
        baked = [e for e in self.ws.history.events() if e["event"] == "baked"]
        self.assertEqual(len(baked), 1)
        self.assertEqual(baked[0]["change_ids"], [initial["change_id"]])
        self.assertEqual(baked[0]["path"], str(self.ws.table().get("@python").root))

    def test_process_exit_between_staging_manifest_and_content_is_recovered(self):
        self.ws.close()
        worker = r'''
import os, sys
from mindslice import Workspace, history
write = history.atomic_write_text
def interrupt(path, text):
    write(path, text)
    if path.name == ".manifest.json":
        os._exit(77)
history.atomic_write_text = interrupt
with Workspace(sys.argv[1]) as ws:
    ws.write("note", summary="Recovered proposal.", stage=True, reason="Keep this explanation.")
'''
        proc = subprocess.run([sys.executable, "-c", worker, str(self.root)],
                              cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 77, proc.stderr)
        self.ws = Workspace(self.root)
        [item] = self.ws.diff()["items"]
        self.assertFalse(item["conflict"])
        self.assertEqual(item["changes"][0]["reason"], "Keep this explanation.")
        self.assertEqual(self.ws.history.events()[0]["event"], "proposed")
        with self.assertRaises(NotFoundError):
            self.ws.read("note")
        self.ws.apply()
        self.assertEqual(self.ws.read("note")["summary"], "Recovered proposal.")
