"""``op="patch"`` (partial edit), ``also`` (several writes in one transaction) and ``read`` of several addresses."""

import json
from unittest.mock import patch

from mindslice import Workspace
from mindslice.errors import InvalidArgumentsError, NotFoundError, PreconditionFailedError
from mindslice.interfaces.mcp_server import MCPServer

from .helpers import WorkspaceTestCase, card_text
from .test_interfaces import run_cli


class PatchTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.ws.write("team/lead", title="Team lead", summary="The lead is Ana.", tags=["team"],
                      content=["Ana leads since 2024.", "Deputy: [[team/deputy]].", "Standup at 09:30."])
        self.file = self.overlay_file("team/lead")

    def test_patch_swaps_only_the_quoted_text(self):
        before = self.file.read_text(encoding="utf-8")
        result = self.ws.write("team/lead", op="patch", reason="Bo took over.", edits=[
            {"old": "The lead is Ana.", "new": "The lead is Bo."},
            {"old": "- Ana leads since 2024.", "new": "- Bo leads since 2026."}])
        self.assertEqual((result["op"], result["changed"], result["staged"]), ("patch", True, False))
        self.assertEqual(self.file.read_text(encoding="utf-8"),
                         before.replace("The lead is Ana.", "The lead is Bo.").replace("Ana leads since 2024", "Bo leads since 2026"))
        event = self.ws.history.events()[-1]
        self.assertEqual((event["op"], event["reason"]), ("patch", "Bo took over."))
        # Edits are applied in order, so a later one may quote what an earlier one wrote.
        self.ws.write("team/lead", op="patch", edits=[["09:30", "10:00"], ["Standup at 10:00.", "Standup at 10:00, room 2."]])
        self.assertIn("- Standup at 10:00, room 2.\n", self.file.read_text(encoding="utf-8"))

    def test_an_edit_that_does_not_match_exactly_once_changes_nothing(self):
        before = self.file.read_bytes()
        with self.assertRaises(PreconditionFailedError) as missing:
            self.ws.write("team/lead", op="patch", edits=[{"old": "Standup at 09:30.", "new": "Standup at 10:00."},
                                                          {"old": "The lead is Cy.", "new": "x"}])
        self.assertEqual((missing.exception.details["edit"], missing.exception.details["occurrences"]), (1, 0))
        with self.assertRaises(PreconditionFailedError) as twice:
            self.ws.write("team/lead", op="patch", edits=[{"old": "Ana", "new": "Bo"}])
        self.assertEqual(twice.exception.details["occurrences"], 2)
        with self.assertRaises(PreconditionFailedError):  # the frontmatter is not searched: fields have their own arguments
            self.ws.write("team/lead", op="patch", edits=[{"old": "Team lead", "new": "Lead"}])
        self.assertEqual(self.file.read_bytes(), before)
        with self.assertRaises(NotFoundError):
            self.ws.write("team/none", op="patch", edits=[{"old": "a", "new": "b"}])

    def test_patch_arguments(self):
        for kwargs in ({"op": "patch"}, {"op": "patch", "edits": []}, {"op": "patch", "edits": [{"old": "", "new": "x"}]},
                       {"op": "patch", "edits": [{"old": "Ana"}]}, {"op": "patch", "edits": [["Ana", "Bo"]], "content": "x"},
                       {"op": "replace", "edits": [["Ana", "Bo"]]}):
            with self.assertRaises(InvalidArgumentsError, msg=kwargs):
                self.ws.write("team/lead", **kwargs)
        # Fields behave as in replace: only the ones passed change.
        self.ws.write("team/lead", op="patch", edits=[["09:30", "10:00"]], tags=["team", "people"])
        card = self.ws.read("team/lead")
        self.assertEqual((card["tags"], card["title"]), (["team", "people"], "Team lead"))
        same = self.ws.write("team/lead", op="patch", edits=[["10:00", "10:00"]], if_match=card["sha256"])
        self.assertFalse(same["changed"])
        with self.assertRaises(PreconditionFailedError):
            self.ws.write("team/lead", op="patch", edits=[["10:00", "11:00"]], if_match="0" * 64)

    def test_patch_of_a_staged_card_edits_the_proposal(self):
        first = self.ws.write("team/lead", op="patch", edits=[["09:30", "10:00"]], stage=True)
        self.assertTrue(first["staged"])
        self.assertIn("09:30", self.file.read_text(encoding="utf-8"))
        self.ws.write("team/lead", op="patch", edits=[["10:00", "10:15"]], stage=True)
        self.ws.apply()
        self.assertIn("- Standup at 10:15.\n", self.file.read_text(encoding="utf-8"))

    def test_patch_of_a_slice_card_quotes_it_as_read_and_saves_a_copy(self):
        root = self.mount_slice("story", {
            "plot/state": card_text("State", "Session one state.", ["fact one", "see [[plot/people]] for names"]),
            "plot/people": card_text("People", "Who is who.", ["Lu is a courier"]),
        }, "@story", 50, "curated")
        original = (root / "plot" / "state.md").read_bytes()
        body = self.ws.read("plot/state")["body"]
        self.assertIn("see [[plot/people]] for names", body)
        result = self.ws.write("plot/state", op="patch",
                               edits=[{"old": "see [[plot/people]] for names", "new": "see [[plot/people]] for the cast"}])
        self.assertEqual((result["address"], result["forked_from"]), ("@overlay/plot/state", "@story/plot/state"))
        text = self.overlay_file("plot/state").read_text(encoding="utf-8")
        self.assertIn("- see [[@story/plot/people]] for the cast\n", text)
        self.assertIn("- fact one\n", text)
        self.assertIn('supersedes = ["@story/plot/state"]', text)
        self.assertEqual((root / "plot" / "state.md").read_bytes(), original)


class BatchTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.ws.write("old/place", title="Place", summary="Where the thing lives.", content=["It lives in room 4."])
        self.ws.write("index", title="Index", summary="Entry points.", content=["See [[old/place]]."])

    def events(self):
        return [(e["event"], e["address"], e["op"]) for e in self.ws.history.events()]

    def restart(self):
        self.ws.close()
        self.ws = Workspace(self.root, lock_timeout=5.0)

    def die_in_batch(self, *writes):
        """The process dies inside a batch after ``writes``: its files are changed and nothing puts them back."""
        with patch.object(type(self.ws.history), "_undo"), self.assertRaises(KeyboardInterrupt):
            with self.ws._writing(), self.ws.history.batch():
                for kwargs in writes:
                    self.ws.write(**kwargs)
                raise KeyboardInterrupt
        self.assertTrue(self.ws.history.batch_path.exists())
        self.restart()

    def test_a_move_is_one_call(self):
        before = len(self.ws.history.events())
        result = self.ws.write(
            "new/place", title="Place", summary="Where the thing lives.", content=["It lives in room 4."],
            reason="Moved under new/.",
            also=[{"id": "old/place", "op": "delete"},
                  {"id": "index", "op": "patch", "edits": [{"old": "[[old/place]]", "new": "[[new/place]]"}],
                   "reason": "Follow the move."}])
        self.assertEqual([r["op"] for r in result["also"]], ["delete", "patch"])
        self.assertTrue(result["changed"] and all(r["changed"] for r in result["also"]))
        self.assertFalse(self.overlay_file("old/place").exists())
        self.assertEqual(self.ws.read("index")["links"], [{"ref": "new/place", "address": "@overlay/new/place"}])
        new = self.ws.history.events()[before:]
        self.assertEqual([(e["address"], e["op"], e["reason"]) for e in new], [
            ("@overlay/new/place", "create", "Moved under new/."),
            ("@overlay/old/place", "delete", "Moved under new/."),  # a member without a reason takes the call's
            ("@overlay/index", "patch", "Follow the move.")])
        # The delete came before the write that repaired the link: on the state the batch leaves, nothing points at it.
        self.assertEqual(result["also"][0].get("affected_backlinks", []), [])
        self.assertFalse(self.ws.history.has_journal())
        report = self.ws.validate()
        self.assertEqual((report["errors"], report["warnings"]), ([], []))

    def test_what_is_left_to_repair_is_still_reported(self):
        result = self.ws.write("new/place", summary="Where the thing lives.", also=[{"id": "old/place", "op": "delete"}])
        self.assertEqual(result["also"][0]["affected_backlinks"], [{"address": "@overlay/index", "links_to": "@overlay/old/place"}])

    def test_a_failed_member_leaves_nothing_behind(self):
        files = {p: p.read_bytes() for p in self.root.joinpath("overlay").rglob("*.md")}
        events = self.events()
        with self.assertRaises(NotFoundError) as caught:
            self.ws.write("new/place", summary="Where the thing lives.", also=[
                {"id": "old/place", "op": "delete"},
                {"id": "index", "op": "patch", "edits": [["[[old/place]]", "[[new/place]]"]]},
                {"id": "missing/card", "op": "append", "content": ["x"]}])
        self.assertEqual(caught.exception.details["failed_write"], {"index": 3, "id": "missing/card"})
        self.assertIn("none of them was saved", caught.exception.message)
        self.assertEqual({p: p.read_bytes() for p in self.root.joinpath("overlay").rglob("*.md")}, files)
        self.assertFalse(self.root.joinpath("overlay", "new").exists())
        self.assertEqual(self.events(), events)
        self.assertFalse(self.ws.history.has_journal())
        self.assertFalse(self.ws.history.batch_path.exists())
        # The index went back with the files.
        self.assertEqual(self.ws.read("index")["links"], [{"ref": "old/place", "address": "@overlay/old/place"}])
        with self.assertRaises(NotFoundError):
            self.ws.read("new/place")
        self.ws.write("new/place", summary="A later write works as usual.")

    def test_members_see_the_ones_before_them(self):
        result = self.ws.write("log", summary="A log.", content=["one"],
                               also=[{"id": "log", "op": "append", "content": ["two"]},
                                     {"id": "log", "op": "patch", "edits": [["- one", "- 1"]]}])
        self.assertEqual(result["also"][0]["previous_sha256"], result["sha256"])
        self.assertEqual(self.ws.read("log")["body"], "- 1\n- two\n")

    def test_member_arguments_are_checked_before_anything_is_written(self):
        for also in ([{"op": "delete"}], [{"id": "x", "stage": True}], [{"id": "x", "also": []}], ["x"], "x"):
            with self.assertRaises((InvalidArgumentsError, TypeError), msg=also):
                self.ws.write("first", summary="First.", also=also)
        with self.assertRaises(InvalidArgumentsError) as caught:  # a member's own bad value names the member too
            self.ws.write("first", summary="First.", also=[{"id": "second", "op": "nope"}])
        self.assertEqual(caught.exception.details["failed_write"]["index"], 1)
        self.assertFalse(self.overlay_file("first").exists())

    def test_a_member_that_changes_standing_memory_is_staged_with_the_rest_saved(self):
        result = self.ws.write("note", summary="A note.", also=[{"id": "prefs/tone", "summary": "Be brief.", "load": "always"}])
        self.assertEqual((result["staged"], result["also"][0]["staged"]), (False, True))
        self.assertIn("requires_approval", result["also"][0])
        self.assertTrue(self.overlay_file("note").exists())
        self.assertEqual([i["id"] for i in self.ws.diff()["items"]], ["prefs/tone"])
        # A failure after a staged member takes the proposal back as well.
        with self.assertRaises(NotFoundError):
            self.ws.write("prefs/voice", summary="Be kind.", load="always", also=[{"id": "nope", "op": "replace", "summary": "x"}])
        self.assertEqual([i["id"] for i in self.ws.diff()["items"]], ["prefs/tone"])
        staged = self.ws.write("a", summary="A.", stage=True, also=[{"id": "b", "summary": "B."}])
        self.assertTrue(staged["staged"] and staged["also"][0]["staged"])

    def test_a_batch_cut_short_by_a_crash_is_undone_on_restart(self):
        files = {p: p.read_bytes() for p in self.root.joinpath("overlay").rglob("*.md")}
        events = self.events()
        self.die_in_batch({"id": "new/place", "summary": "Where the thing lives."}, {"id": "old/place", "op": "delete"},
                          {"id": "index", "op": "patch", "edits": [["[[old/place]]", "[[new/place]]"]]})
        self.assertFalse(self.overlay_file("old/place").exists())
        self.assertTrue(self.ws.history.has_journal())
        self.assertEqual(self.ws.read("index")["links"], [{"ref": "old/place", "address": "@overlay/old/place"}])
        self.assertEqual({p: p.read_bytes() for p in self.root.joinpath("overlay").rglob("*.md")}, files)
        self.assertEqual(self.events(), events)
        self.assertFalse(self.ws.history.has_journal())

    def test_a_batch_that_was_decided_is_finished_on_restart(self):
        from mindslice.storage.history import unlink_if_exists as unlink

        def stop(path):
            if path == self.ws.history.batch_path:
                raise OSError("crashed after the batch was decided")
            return unlink(path)

        with patch("mindslice.storage.history.unlink_if_exists", side_effect=stop):
            with self.assertRaises(OSError):
                self.ws.write("new/place", summary="Where the thing lives.", also=[{"id": "old/place", "op": "delete"}])
        self.assertTrue(self.ws.history.batch_path.exists() and self.ws.history.journal_path.exists())
        self.restart()
        self.assertEqual(self.ws.read("new/place")["summary"], "Where the thing lives.")
        self.assertFalse(self.overlay_file("old/place").exists())
        self.assertEqual(self.events()[-2:], [("applied", "@overlay/new/place", "create"), ("applied", "@overlay/old/place", "delete")])
        self.assertFalse(self.ws.history.has_journal())

    def test_an_undo_never_overwrites_a_file_changed_outside_the_batch(self):
        from mindslice.errors import HistoryError

        self.die_in_batch({"id": "index", "op": "patch", "edits": [["[[old/place]]", "[[new/place]]"]]})
        self.overlay_file("index").write_text("edited by hand\n", encoding="utf-8")
        with self.assertRaises(HistoryError):
            self.ws.read("index")
        self.assertEqual(self.overlay_file("index").read_text(encoding="utf-8"), "edited by hand\n")
        self.assertTrue(self.ws.history.batch_path.exists())


class ReadManyTests(WorkspaceTestCase):
    def test_cards_come_back_in_the_order_asked_with_errors_in_place(self):
        self.ws.write("a", summary="Card A.")
        self.ws.write("b", summary="Card B.", content=["See [[a]]."])
        result = self.ws.read(["b", "missing", "@overlay/a"])
        self.assertEqual(result["total"], 3)
        self.assertEqual([c.get("address") for c in result["cards"]], ["@overlay/b", None, "@overlay/a"])
        self.assertEqual((result["cards"][1]["requested"], result["cards"][1]["code"]), ("missing", "not_found"))
        self.assertEqual(result["cards"][2], {**self.ws.read("a"), "requested": "@overlay/a",
                                              "read_count": result["cards"][2]["read_count"],
                                              "last_read_at": result["cards"][2]["last_read_at"]})
        self.assertEqual(self.ws.read([]), {"cards": [], "total": 0})


class InterfaceTests(WorkspaceTestCase):
    def tool(self, server, name, **arguments):
        res = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
        return res["result"]["isError"], json.loads(res["result"]["content"][0]["text"])

    def test_mcp(self):
        server = MCPServer(self.ws)
        self.assertFalse(self.tool(server, "write", id="a", summary="Card A.", content=["one", "two"])[0])
        err, res = self.tool(server, "write", id="a", op="patch", edits=[{"old": "- one", "new": "- uno"}],
                             also=[{"id": "b", "summary": "Card B."}])
        self.assertFalse(err, res)
        self.assertEqual((res["op"], res["also"][0]["address"]), ("patch", "@overlay/b"))
        err, res = self.tool(server, "read", address=["a", "b", "c"])
        self.assertFalse(err)
        self.assertEqual([c.get("body", c.get("code")) for c in res["cards"]], ["- uno\n- two\n", "", "not_found"])
        err, res = self.tool(server, "write", id="a", op="patch", edits=[{"old": "- one", "new": "- 1"}],
                             also=[{"id": "c", "summary": "Card C."}])
        self.assertTrue(err)
        self.assertEqual((res["code"], res["details"]["failed_write"]["index"]), ("precondition_failed", 0))
        err, res = self.tool(server, "write", id="c", summary="Card C.", also=[{"id": "d", "body": "x"}])
        self.assertEqual((err, res["code"]), (True, "invalid_arguments"))
        self.assertTrue(self.tool(server, "read", address="c")[0])
        # A server that stages every write stages every member.
        err, res = self.tool(MCPServer(self.ws, stage_writes=True), "write", id="c", summary="Card C.",
                             also=[{"id": "a", "op": "delete"}])
        self.assertEqual((err, res["staged"], res["also"][0]["staged"]), (False, True, True))

    def test_cli(self):
        w = str(self.root)
        self.assertEqual(run_cli("-w", w, "write", "a", "--summary", "Card A.", "--content", "- one\n- two")[0], 0)
        code, out, _ = run_cli("-w", w, "write", "a", "--op", "patch", "--edit", "- one", "- uno", "--edit", "Card A.", "Card A!")
        self.assertEqual(code, 0)
        self.assertIn("Patched @overlay/a", out)
        also = self.tmp / "also.json"
        also.write_text(json.dumps([{"id": "a", "op": "delete"}]), encoding="utf-8")
        code, out, _ = run_cli("-w", w, "write", "b", "--summary", "Card B.", "--content", "- uno", "--also", str(also))
        self.assertEqual(code, 0)
        self.assertIn("Created @overlay/b", out)
        self.assertIn("Deleted @overlay/a", out)
        self.ws.write("c", summary="Card C.")
        code, out, _ = run_cli("-w", w, "read", "b", "a", "c")
        self.assertEqual(code, 0)
        self.assertLess(out.index("# B"), out.index("error [not_found]"))
        self.assertLess(out.index("error [not_found]"), out.index("# C"))
        code, out, _ = run_cli("-w", w, "--json", "read", "b", "c")
        self.assertEqual([c["address"] for c in json.loads(out)["cards"]], ["@overlay/b", "@overlay/c"])
        code, _, err = run_cli("-w", w, "write", "b", "--op", "patch", "--edit", "nope", "x")
        self.assertEqual(code, 1)
        self.assertIn("precondition_failed", err)
