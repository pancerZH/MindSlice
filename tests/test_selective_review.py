"""Partial approval must preserve deferred work, dependencies, and crash recovery."""

import io
import json
from unittest.mock import patch

from mindslice import ApplyConflictError, InvalidArgumentsError, Workspace
from mindslice.interfaces.staging_review import run
from mindslice.operations import staging

from .helpers import WorkspaceTestCase, card_text
from .test_interfaces import run_cli


class SelectiveReviewTests(WorkspaceTestCase):
    def stage(self, path, **kwargs):
        return self.ws.write(path, summary=f"Proposal for {path}.", stage=True, reason=f"Reason for {path}.", **kwargs)

    def test_selective_apply_preserves_other_manifests_files_and_reasons(self):
        self.stage("a")
        self.stage("b")
        before = self.ws.staging.file("b").read_bytes()
        entry = self.ws.staging.load_manifest()["b"]
        result = self.ws.apply(["@overlay/a.md"])
        self.assertEqual(result["created"], ["@overlay/a"])
        self.assertEqual(self.ws.staging.load_manifest(), {"b": entry})
        self.assertEqual(self.ws.staging.file("b").read_bytes(), before)
        self.assertEqual(self.ws.diff()["items"][0]["changes"][0]["reason"], "Reason for b.")
        self.assertEqual(self.ws.apply()["created"], ["@overlay/b"])

    def test_discard_subset_preserves_live_cards_tombstones_and_orphans(self):
        self.ws.write("live", summary="Live memory.")
        self.ws.write("live", op="delete", stage=True)
        self.stage("reject")
        orphan = self.ws.staging.file("orphan")
        orphan.write_text(card_text("Orphan", "Manual draft."))
        self.assertEqual(self.ws.discard(["reject"])["ids"], ["reject"])
        self.assertTrue(self.overlay_file("live").exists())
        self.assertEqual(set(self.ws.staging.entries()), {"live", "orphan"})
        self.ws.apply(["orphan"])
        self.assertEqual(set(self.ws.staging.entries()), {"live"})
        self.ws.apply(["live"])
        self.assertFalse(self.overlay_file("live").exists())

    def test_invalid_selection_and_empty_selection_never_apply_everything(self):
        self.stage("a")
        for selection in (["missing"], ["@other/a"], ["../a"], "a"):
            with self.assertRaises((InvalidArgumentsError, ValueError)):
                self.ws.apply(selection)
            with self.assertRaises((InvalidArgumentsError, ValueError)):
                self.ws.discard(selection)
        self.assertEqual(self.ws.apply([])["applied"], 0)
        self.assertEqual(self.ws.discard([])["discarded"], 0)
        self.assertEqual(set(self.ws.staging.entries()), {"a"})

    def test_conflict_on_unselected_card_does_not_block_an_independent_approval(self):
        self.stage("a")
        self.stage("b")
        self.put_overlay("b", card_text("B", "External edit."))
        self.ws.apply(["a"])
        self.assertTrue(self.ws.diff()["items"][0]["conflict"])

    def test_staged_dependencies_include_links_lineage_and_card_aliases(self):
        self.stage("target", aliases=["named target"])
        self.stage("extension", extends=["named target"])
        self.stage("link", content="Read [[@overlay/target]].")
        for path in ("extension", "link"):
            with self.assertRaises(ApplyConflictError) as ctx:
                self.ws.apply([path])
            self.assertEqual(ctx.exception.details["conflicts"][0]["target"], "@overlay/target")
            self.assertFalse(self.overlay_file(path).exists())
        self.ws.apply(["target", "extension", "link"])
        self.assertTrue(self.ws.validate()["ok"])

    def test_live_baseline_is_sufficient_even_if_it_has_a_pending_edit(self):
        self.ws.write("target", summary="Existing baseline.")
        self.ws.write("target", op="replace", summary="New proposal.", stage=True)
        self.stage("link", extends=["target"])
        self.ws.apply(["link"])
        self.assertEqual(set(self.ws.staging.entries()), {"target"})

    def test_partial_delete_cannot_break_live_reference_but_combined_edit_can_fix_it(self):
        self.ws.write("target", summary="Existing target.")
        self.ws.write("link", summary="Read [[target]].")
        self.ws.write("target", op="delete", stage=True)
        self.ws.write("link", op="replace", summary="No longer references the target.", stage=True)
        with self.assertRaises(ApplyConflictError):
            self.ws.apply(["target"])
        self.ws.apply(["target", "link"])
        self.assertTrue(self.ws.validate()["ok"])

    def test_preexisting_dangling_reference_does_not_block_unrelated_review(self):
        self.ws.write("old", summary="Read [[missing]].")
        self.stage("independent")
        self.assertEqual(self.ws.apply(["independent"])["applied"], 1)

    def test_rejecting_dependency_and_accepting_referrer_changes_nothing(self):
        self.stage("target")
        self.stage("link", extends=["target"])
        with self.assertRaises(ApplyConflictError):
            self.ws.review(["link"], ["target"], revision=self.ws.diff()["revision"])
        self.assertEqual(set(self.ws.staging.entries()), {"target", "link"})
        self.assertFalse(self.overlay_file("link").exists())

    def test_review_rechecks_content_and_decisions_before_mutation(self):
        self.stage("a")
        self.stage("b")
        revision = self.ws.diff()["revision"]
        self.ws.write("b", op="append", content="- New information.", stage=True)
        with self.assertRaises(ApplyConflictError):
            self.ws.review(["a"], ["b"], revision=revision)
        with self.assertRaises(InvalidArgumentsError):
            self.ws.review(["a"], ["a"], revision=self.ws.diff()["revision"])
        self.assertEqual(set(self.ws.staging.entries()), {"a", "b"})

    def test_selected_apply_and_reject_recover_without_losing_deferred_work(self):
        for path in ("accept", "reject", "defer"):
            self.stage(path)
        entry = self.ws.staging.load_manifest()["defer"]
        original_append = self.ws.history.append
        calls = 0

        def interrupt(events):
            nonlocal calls
            original_append(events)
            calls += 1
            if calls == 2:
                raise OSError("simulated interruption after reject history append")

        with patch.object(self.ws.history, "append", side_effect=interrupt):
            with self.assertRaises(OSError):
                self.ws.review(["accept"], ["reject"], revision=self.ws.diff()["revision"])
        with Workspace(self.root) as recovered:
            recovered.status()
            self.assertEqual(recovered.staging.load_manifest(), {"defer": entry})
            self.assertEqual([i["id"] for i in recovered.diff()["items"]], ["defer"])
            events = recovered.history.events()
            self.assertEqual(len([e for e in events if e["event"] == "applied"]), 1)
            self.assertEqual(len([e for e in events if e["event"] == "discarded"]), 1)
            self.assertTrue(self.overlay_file("accept").exists())

    def test_partial_discard_recovers_without_removing_other_proposals(self):
        self.stage("a")
        self.stage("b")
        with patch.object(self.ws.history, "append", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                self.ws.discard(["a"])
        self.ws.status()
        self.assertEqual(set(self.ws.staging.entries()), {"b"})

    def test_apply_recovery_keeps_skipped_and_unselected_entries(self):
        self.stage("a")
        self.stage("b")
        with patch.object(staging, "durable_move", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                self.ws.apply(["a"])
        self.put_overlay("a", card_text("A", "Concurrent external change."))
        self.ws.status()
        self.assertEqual(set(self.ws.staging.entries()), {"a", "b"})
        self.assertTrue(self.ws.last_recovery["skipped"])

    def test_cli_selection_and_interactive_accept_reject_leave(self):
        for path in ("a", "b", "c"):
            self.stage(path)
        with patch("sys.stdin", io.StringIO("accept\nreject\nleave\nyes\n")), \
                patch("sys.stdin.isatty", return_value=True), patch("sys.stderr", io.StringIO()) as err:
            result = run(self.ws)
        self.assertEqual(result["created"], ["@overlay/a"])
        self.assertEqual(result["discarded_ids"], ["b"])
        self.assertEqual(result["remaining"], 1)
        self.assertIn("Reason for a.", err.getvalue())
        code, out, _ = run_cli("-w", str(self.root), "--json", "apply", "c")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["created"], ["@overlay/c"])
        self.stage("d")
        code, out, _ = run_cli("-w", str(self.root), "--json", "discard", "@overlay/d")
        self.assertEqual(json.loads(out)["discarded"], 1)

    def test_cancel_and_eof_leave_all_choices_unexecuted(self):
        self.stage("a")
        self.stage("b")
        for answers in ("accept\ncancel\n", "accept\n", "accept\nreject\nno\n"):
            with patch("sys.stdin", io.StringIO(answers)), patch("sys.stdin.isatty", return_value=True), \
                    patch("sys.stderr", io.StringIO()):
                self.assertTrue(run(self.ws)["cancelled"])
            self.assertEqual(set(self.ws.staging.entries()), {"a", "b"})

    def test_review_requires_terminal_instead_of_reading_piped_choices(self):
        self.stage("a")
        code, _, err = run_cli("-w", str(self.root), "review", stdin="accept\nyes\n")
        self.assertEqual(code, 1)
        self.assertIn("interactive terminal", err)

    def test_preflight_is_read_only_and_reports_all_choices_and_live_impact(self):
        self.ws.write("base", summary="Existing base.")
        self.ws.write("dependent", summary="See [[base]].", extends=["base"])
        self.ws.write("base", op="replace", summary="Proposed base edit.", stage=True)
        self.stage("reject")
        self.stage("later")
        snapshot = self.ws.diff()
        base = next(i for i in snapshot["items"] if i["id"] == "base")
        self.assertEqual(base["impact"]["affected_backlinks"][0]["address"], "@overlay/dependent")
        self.assertEqual(base["impact"]["affected_extensions"][0]["address"], "@overlay/dependent")
        history_before = self.ws.history.events()
        plan = self.ws.review(["base"], ["reject"], revision=snapshot["revision"], dry_run=True)
        self.assertTrue(plan["ready"])
        self.assertEqual(plan["pending"], ["later"])
        self.assertEqual(self.ws.diff(), snapshot)
        self.assertEqual(self.ws.history.events(), history_before)

    def test_interactive_dependency_block_is_shown_before_confirm_and_can_be_revised(self):
        self.stage("a", extends=["b"])
        self.stage("b")
        # First accept A and leave B. Then review again, accepting both.
        answers = "accept\nleave\nyes\naccept\naccept\nyes\n"
        with patch("sys.stdin", io.StringIO(answers)), patch("sys.stdin.isatty", return_value=True), \
                patch("sys.stderr", io.StringIO()) as err:
            result = run(self.ws)
        self.assertEqual(result["applied"], 2)
        output = err.getvalue()
        self.assertIn("Blocked:", output)
        self.assertEqual(output.count("Execute these choices?"), 1)
        self.assertLess(output.index("Blocked:"), output.index("Execute these choices?"))

    def test_edit_during_final_confirmation_invalidates_review(self):
        self.stage("a")
        snapshot = self.ws.staging.file("a").read_text()

        def answer(prompt):
            if prompt.startswith("Execute"):
                self.ws.write("a", op="append", content="- Arrived during review.", stage=True)
                return "yes"
            return "accept"

        with patch("sys.stdin.isatty", return_value=True), patch("sys.stderr", io.StringIO()), \
                patch("mindslice.interfaces.staging_review._answer", side_effect=answer):
            with self.assertRaises(ApplyConflictError):
                run(self.ws)
        self.assertFalse(self.overlay_file("a").exists())
        self.assertNotEqual(self.ws.staging.file("a").read_text(), snapshot)

    def test_execution_interrupt_is_not_misreported_as_cancelled(self):
        self.stage("a")
        real_review = self.ws.review

        def interrupted(*args, **kwargs):
            if kwargs.get("dry_run"):
                return real_review(*args, **kwargs)
            raise KeyboardInterrupt

        with patch("sys.stdin", io.StringIO("accept\nyes\n")), patch("sys.stdin.isatty", return_value=True), \
                patch("sys.stderr", io.StringIO()) as err, patch.object(self.ws, "review", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                run(self.ws)
        self.assertNotIn("no review choices were executed", err.getvalue())
